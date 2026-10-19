# Deploy no EKS — Central de Chamados

Este procedimento publica a Central de Chamados no cluster EKS. A aplicação
usa PostgreSQL externo ao container; o servidor e o banco PostgreSQL devem
estar provisionados e acessíveis pela rede antes do deploy. Em uma instalação
inicial, o banco pode estar vazio: a aplicação cria as tabelas ao iniciar.
Não há etapa de cópia do antigo SQLite. O Deployment permanece com uma réplica
porque o limitador de login e a tarefa de segundo plano são mantidos em memória.

## Dados definidos

| Item | Valor |
| --- | --- |
| Namespace | `prd-central-chamados` |
| URL | `https://chamados.hospitalriogrande.com.br` |
| Imagem | `911107441482.dkr.ecr.sa-east-1.amazonaws.com/centralservicos-frontend` |
| Plataforma | `linux/arm64` |
| Banco | PostgreSQL externo, host e credenciais no Secret `central-chamados-secrets` |

## Pré-requisitos

1. O CNAME `chamados.hospitalriogrande.com.br` deve apontar para o Load
   Balancer NGINX já usado pelo cluster.
2. A sessão AWS precisa estar autenticada com MFA e ter acesso ao ECR.
3. A máquina de build precisa ter Docker com Buildx e suporte a `linux/arm64`.
4. O contexto Kubernetes precisa ser `hrg-prod-eks`.
5. Um banco PostgreSQL vazio ou dedicado precisa existir, com database e
   usuário criados, e aceitar conexões originadas do cluster EKS.

Confirme os acessos antes de criar recursos:

```powershell
aws sts get-caller-identity
kubectl config current-context
```

## 1. Construir e enviar a imagem

Na raiz deste repositório, escolha uma tag nova no formato `AAAA-MM-DD-N`:

```powershell
$region = 'sa-east-1'
$accountId = '911107441482'
$repository = 'centralservicos-frontend'
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

## 2. Criar namespace e segredos

Esta etapa cria recursos de produção e os valores informados entram no ambiente
da aplicação. Não grave os valores em arquivos ou no Git.

```powershell
kubectl apply -f k8s/namespace.yaml

$secretKey = python -c "import secrets; print(secrets.token_hex(32))"
$pgHost = Read-Host 'Host ou endpoint do PostgreSQL'
$pgPort = Read-Host 'Porta do PostgreSQL (normalmente 5432)'
$pgDatabase = Read-Host 'Nome do banco PostgreSQL'
$pgUser = Read-Host 'Usuário do PostgreSQL'
$pgPasswordSecure = Read-Host 'Senha do PostgreSQL' -AsSecureString
$hotelariaUsuario = Read-Host 'Usuário administrativo da Hotelaria'
$hotelariaSenha = Read-Host 'Senha administrativa da Hotelaria' -AsSecureString
$enfermagemUsuario = Read-Host 'Usuário administrativo da Enfermagem'
$enfermagemSenha = Read-Host 'Senha administrativa da Enfermagem' -AsSecureString

# Converta as senhas apenas em memória para enviar ao Kubernetes.
$hotelariaPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($hotelariaSenha)
$enfermagemPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($enfermagemSenha)
$pgPasswordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pgPasswordSecure)
try {
  $pgPasswordTexto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pgPasswordPtr)
  $hotelariaSenhaTexto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($hotelariaPtr)
  $enfermagemSenhaTexto = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($enfermagemPtr)

  kubectl -n prd-central-chamados create secret generic central-chamados-secrets `
    --from-literal=SECRET_KEY=$secretKey `
    --from-literal=PGHOST=$pgHost `
    --from-literal=PGPORT=$pgPort `
    --from-literal=PGDATABASE=$pgDatabase `
    --from-literal=PGUSER=$pgUser `
    --from-literal=PGPASSWORD=$pgPasswordTexto `
    --from-literal=HOTELARIA_USUARIO=$hotelariaUsuario `
    --from-literal=HOTELARIA_SENHA=$hotelariaSenhaTexto `
    --from-literal=ENFERMAGEM_USUARIO=$enfermagemUsuario `
    --from-literal=ENFERMAGEM_SENHA=$enfermagemSenhaTexto
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($hotelariaPtr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($enfermagemPtr)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pgPasswordPtr)
  Remove-Variable pgPasswordTexto -ErrorAction SilentlyContinue
}
```

O Secret guarda as configurações de conexão do PostgreSQL e as credenciais
administrativas. O banco pode estar vazio; não importe o arquivo SQLite antigo.

## 3. Validar e publicar os manifestos

Atualize a tag da imagem em `k8s/deployment.yaml`, valide o manifesto no
servidor e só então aplique. Na primeira inicialização, a aplicação conecta
ao PostgreSQL e cria as tabelas necessárias.

```powershell
$renderizado = kubectl kustomize k8s

$renderizado | kubectl apply --dry-run=server -f -
$renderizado | kubectl apply -f -
kubectl -n prd-central-chamados rollout status deployment/central-chamados --timeout=5m
```

## 4. Validar a publicação

```powershell
kubectl -n prd-central-chamados get deployment,pods,service,ingress
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

O rollback não altera o banco PostgreSQL. Um PVC que tenha sido criado pela
versão anterior com SQLite não é mais usado pelo Deployment; não o exclua sem
confirmar se ainda precisa ser preservado.
