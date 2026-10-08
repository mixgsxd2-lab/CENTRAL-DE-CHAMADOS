# Deploy no EKS — Central de Chamados

Este procedimento publica a Central de Chamados com SQLite persistente no
cluster EKS. O ambiente de produção usa uma réplica única e um volume EBS;
não escale o Deployment horizontalmente enquanto o banco for SQLite.

## Dados definidos

| Item | Valor |
| --- | --- |
| Namespace | `prd-central-chamados` |
| URL | `https://chamados.hospitalriogrande.com.br` |
| Imagem | `911107441482.dkr.ecr.sa-east-1.amazonaws.com/central-de-chamados` |
| Plataforma | `linux/arm64` |
| Dados | PVC `central-chamados-data`, StorageClass `gp3`, 5 GiB |

## Pré-requisitos

1. O CNAME `chamados.hospitalriogrande.com.br` deve apontar para o Load
   Balancer NGINX já usado pelo cluster.
2. A sessão AWS precisa estar autenticada com MFA e ter acesso ao ECR.
3. A máquina de build precisa ter Docker com Buildx e suporte a `linux/arm64`.
4. O contexto Kubernetes precisa ser `hrg-prod-eks`.

Confirme os acessos antes de criar recursos:

```powershell
aws sts get-caller-identity
kubectl config current-context
kubectl get storageclass gp3
```

## 1. Criar o repositório ECR

Execute uma única vez, já com a sessão AWS MFA válida:

```powershell
aws ecr create-repository `
  --repository-name central-de-chamados `
  --image-tag-mutability IMMUTABLE `
  --image-scanning-configuration scanOnPush=true `
  --region sa-east-1
```

Se o repositório já existir, o comando retorna erro `RepositoryAlreadyExistsException` e nenhuma ação adicional é necessária.

## 2. Construir e enviar a imagem

Na raiz deste repositório, escolha uma tag nova no formato `AAAA-MM-DD-N`:

```powershell
$region = 'sa-east-1'
$accountId = '911107441482'
$repository = 'central-de-chamados'
$tag = 'AAAA-MM-DD-1'
$image = "$accountId.dkr.ecr.$region.amazonaws.com/$repository`:$tag"

docker buildx build --platform linux/arm64 --load -t "$repository`:$tag" .
docker run --rm -d --name central-chamados-test -p 8005:8000 "$repository`:$tag"
curl.exe -i http://localhost:8005/healthz
docker stop central-chamados-test

aws ecr get-login-password --region $region |
  docker login --username AWS --password-stdin "$accountId.dkr.ecr.$region.amazonaws.com"
docker tag "$repository`:$tag" $image
docker push $image
aws ecr describe-images --repository-name $repository --image-ids imageTag=$tag --region $region
```

O teste de saúde deve responder `200` e `ok`. Registre o digest exibido após o
push; a tag é imutável e servirá como referência para rollback.

## 3. Criar namespace e segredos

Esta etapa cria recursos de produção e os valores informados entram no ambiente
da aplicação. Não grave os valores em arquivos ou no Git.

```powershell
kubectl apply -f k8s/namespace.yaml

$secretKey = python -c "import secrets; print(secrets.token_hex(32))"
$hotelariaUsuario = Read-Host 'Usuário administrativo da Hotelaria'
$hotelariaSenha = Read-Host 'Senha administrativa da Hotelaria' -AsSecureString
$enfermagemUsuario = Read-Host 'Usuário administrativo da Enfermagem'
$enfermagemSenha = Read-Host 'Senha administrativa da Enfermagem' -AsSecureString

# Converta as duas senhas apenas em memória para enviar ao Kubernetes.
$hotelariaPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($hotelariaSenha)
$enfermagemPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($enfermagemSenha)
try {
  $hotelariaSenhaTexto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($hotelariaPtr)
  $enfermagemSenhaTexto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($enfermagemPtr)

  kubectl -n prd-central-chamados create secret generic central-chamados-secrets `
    --from-literal=SECRET_KEY=$secretKey `
    --from-literal=HOTELARIA_USUARIO=$hotelariaUsuario `
    --from-literal=HOTELARIA_SENHA=$hotelariaSenhaTexto `
    --from-literal=ENFERMAGEM_USUARIO=$enfermagemUsuario `
    --from-literal=ENFERMAGEM_SENHA=$enfermagemSenhaTexto
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($hotelariaPtr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($enfermagemPtr)
}
```

## 4. Validar e publicar os manifestos

Substitua a tag temporária no manifesto renderizado, valide no servidor e só
então aplique. O primeiro início do Pod cria o arquivo SQLite e as tabelas no
PVC vazio.

```powershell
$image = '911107441482.dkr.ecr.sa-east-1.amazonaws.com/central-de-chamados:AAAA-MM-DD-1'
$renderizado = kubectl kustomize k8s
$renderizado = $renderizado.Replace(
  '911107441482.dkr.ecr.sa-east-1.amazonaws.com/central-de-chamados:REPLACE_ME',
  $image
)

$renderizado | kubectl apply --dry-run=server -f -
$renderizado | kubectl apply -f -
kubectl -n prd-central-chamados rollout status deployment/central-chamados --timeout=5m
```

## 5. Validar a publicação

```powershell
kubectl -n prd-central-chamados get deployment,pods,service,pvc,ingress
kubectl -n prd-central-chamados logs deployment/central-chamados --tail=100
curl.exe -i https://chamados.hospitalriogrande.com.br/healthz
```

O certificado é emitido pelo cert-manager depois que o DNS estiver propagado.
Valide também o portal, os dois logins administrativos e a criação de um
chamado de teste.

## Rollback

Se a nova imagem falhar depois do rollout, reverta apenas o Deployment:

```powershell
kubectl -n prd-central-chamados rollout undo deployment/central-chamados
kubectl -n prd-central-chamados rollout status deployment/central-chamados --timeout=5m
```

O rollback não remove o PVC nem o banco SQLite.
