# Relatório de segurança e stack da Central de Chamados

## Conclusão executiva

O sistema é uma aplicação web Flask monolítica que reúne as centrais de Enfermagem e Hotelaria no mesmo processo e no mesmo banco SQLite. A imagem para EKS foi preparada para ARM64 e possui controles de contêiner adequados, mas **não deve ser exposta publicamente antes da correção dos itens críticos e altos abaixo**.

Os riscos principais são: APIs de Hotelaria expostas sem autenticação, consulta de chamados de Enfermagem sem controle de acesso, credenciais fracas de demonstração presentes no código e um token único de QR Code que pode ser reutilizado para agir em qualquer leito válido.

Escopo: código na revisão `1ff67d34ab2ce90329aedcaf19624ee9887991d0`, manifests Kubernetes e arquivos de build. Esta é uma revisão estática: não foram executados testes de invasão, análise dinâmica, nem varredura de CVEs em dependências.

## Stack e componentes

| Camada | Tecnologia | Uso |
|---|---|---|
| Aplicação | Python 3.12 | Imagem base `python:3.12-slim` |
| Framework web | Flask 3.1.3 | Páginas, API JSON, sessão por cookie assinado |
| Servidor HTTP | Gunicorn 23.0.0 | 1 worker e 4 threads, porta 8000 |
| Banco de dados | SQLite | Arquivo único em `/data/hospital_rio_grande.db`, modo WAL |
| Geração de QR Code | qrcode 8.2 | Geração de QR Codes SVG para acesso dos pacientes |
| Fuso horário | tzdata | Suporte ao fuso `America/Fortaleza` |
| Orquestração | Kubernetes em EKS | 1 réplica, NGINX Ingress, cert-manager, PVC EBS gp3 |
| Registro de imagens planejado | Amazon ECR | Repositório compartilhado `centralservicos-frontend`, com tag exclusiva da aplicação |

Não há ORM, autenticação corporativa, SSO, MFA de usuários da aplicação, cache distribuído, fila, Redis, banco gerenciado, WAF, rate limit no Ingress, lockfile de dependências ou pipeline de análise de segurança identificado no repositório.

## Recursos e dados tratados

O banco contém chamadas de Enfermagem e Hotelaria. Entre os campos retornados pelas APIs estão andar, leito, categoria, subcategoria, descrição/detalhe, estado da solicitação, profissional responsável, horários, avaliação e comentários. Mesmo sem nome do paciente, a associação de leito, horário e motivo de um chamado é dado operacional sensível e pode ser dado pessoal em contexto hospitalar.

O arquivo `hospital_rio_grande.db` está versionado no Git. Ele não é copiado para a imagem porque o `.dockerignore` exclui `*.db`, mas continua acessível a qualquer pessoa com leitura do repositório e preserva seu histórico no Git.

## Achados de segurança

| Prioridade | Achado | Evidência e impacto | Ação necessária |
|---|---|---|---|
| Crítica | APIs de Hotelaria sem autenticação ou vínculo ao leito | `hotelaria/routes.py` expõe criação, consulta por ID e leito, mensagens, confirmação e avaliação sem decorator de autenticação. Um usuário externo pode enumerar IDs, ler chamados, enviar mensagens como `central`, avaliar e confirmar solicitações de terceiros. | Proteger todas as rotas de paciente com uma sessão vinculada ao leito e validar que o chamado pertence ao leito da sessão. Rotas administrativas devem exigir sessão administrativa e papel apropriado. |
| Alta | Consulta de chamado de Enfermagem exposta | `GET /api/enfermagem/chamados/<id>` não tem `@login_requerido` nem `@acesso_paciente_requerido` e serializa leito, categoria, detalhes, profissional e avaliação. | Exigir autenticação administrativa ou uma sessão de paciente vinculada ao mesmo leito. Retornar uma visão mínima específica ao paciente. |
| Alta | Avaliação de Enfermagem sem autorização | `POST /api/enfermagem/chamados/<id>/avaliar` não exige sessão. Um terceiro pode registrar a única avaliação permitida para qualquer chamado finalizado. | Exigir sessão válida do paciente e verificar a propriedade pelo leito antes de avaliar. |
| Alta | QR Code usa um único token global e aceita leito controlado pela URL | O token é fixo e único em `enfermagem_config`; a URL aceita `andar` e `leito` como query string. Quem possuir um QR Code pode trocar esses parâmetros por outro leito válido e obter sessão daquele leito. | Usar segredo aleatório por leito, armazenado como hash; validar que o token corresponde ao leito; prever rotação e revogação. |
| Alta | Credenciais padrão conhecidas e exibidas na interface | `config.py`, `docker-compose.yaml`, README e telas de login trazem `admin`/`12345` e `enfermagem`/`12345`. Se os Secrets do Kubernetes não forem criados ou forem mal configurados, o acesso administrativo fica trivial. | Remover valores padrão de produção e as dicas nas telas. Falhar na inicialização se variáveis obrigatórias estiverem ausentes ou fracas. Migrar para contas individuais com senhas armazenadas com hash ou, preferencialmente, SSO corporativo. |
| Alta | Chave padrão de sessão previsível | `SECRET_KEY` tem fallback fixo no código. Com ela, um atacante pode forjar cookies de sessão Flask. | Não manter fallback em produção; exigir `SECRET_KEY` aleatória, longa e exclusiva no Secret Kubernetes; adicionar validação de inicialização. |
| Média | Banco SQLite versionado no repositório | `hospital_rio_grande.db` está rastreado pelo Git e o `.gitignore` não exclui o arquivo na raiz. O histórico pode conter dados e o token global de QR Code. | Verificar o conteúdo, remover o banco do índice e do histórico se houver dados reais, adicionar regras ao `.gitignore` e rotacionar o token de QR Code se o banco tiver sido compartilhado. Esta ação exige planejamento, pois pode invalidar QR Codes existentes. |
| Média | Sem proteção CSRF explícita | A aplicação usa cookies de sessão e não possui token CSRF ou validação de `Origin`/`Referer`. `SameSite=Lax` reduz parte do risco, mas não substitui uma proteção explícita para operações de escrita. | Adotar tokens CSRF nas rotas de formulário e APIs autenticadas, ou validar estritamente `Origin` para requisições mutáveis com uma política documentada. |
| Média | Rate limit baseado no IP visto pela aplicação | O login usa `request.remote_addr`. Atrás do NGINX Ingress, esse endereço pode ser o IP do proxy, fazendo todos os usuários compartilharem o mesmo limite de 8 tentativas em 5 minutos. | Configurar corretamente a confiança em cabeçalhos encaminhados no proxy ou aplicar rate limit no Ingress/WAF. Preferir rate limit compartilhado se houver escalabilidade futura. |
| Média | Ausência de controle de autorização por função | As duas áreas possuem apenas booleanos de sessão. Não há usuário individual, papel, trilha de auditoria confiável ou separação entre operadores. | Definir papéis mínimos, contas individuais e registrar login, mudanças de status, expiração de acessos e alterações de leitos com usuário e data. |
| Média | Dependências sem lockfile e sem processo SCA | Há apenas `requirements.txt`; `tzdata` não possui versão fixada e não foi identificado scanner de dependências. | Fixar versões, gerar lockfile e adicionar varredura automatizada de CVEs e imagem no pipeline. O scan do ECR no push ajuda, mas não substitui análise antes do deploy. |
| Baixa | Logout aceita GET | As rotas de logout recebem GET; isso permite logout forçado por terceiro, embora sem comprometimento de conta. | Usar POST protegido por CSRF para logout. |

## Controles já presentes

- O Dockerfile executa a aplicação como usuário não-root (`uid 10001`).
- O pod proposto usa `runAsNonRoot`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault` e limites de CPU/memória.
- O banco é montado em PVC separado; ele não é incluído na imagem.
- O Ingress proposto força HTTPS, usa cert-manager e limita corpos a 256 KB.
- A aplicação define `HttpOnly`, `SameSite=Lax`, `MAX_CONTENT_LENGTH`, cabeçalhos CSP, `X-Content-Type-Options`, `X-Frame-Options` e `Referrer-Policy`.
- As operações SQL analisadas usam parâmetros para valores externos. Os únicos SQLs construídos dinamicamente identificados usam listas internas de colunas/tabelas, não entrada direta do usuário.
- Há limite de tentativas de login e validação de tamanho para vários campos livres.
- O manifesto define uma única réplica e estratégia `Recreate`, coerentes com SQLite em volume `ReadWriteOnce`.

## Limitações arquiteturais relevantes

SQLite em EBS funciona para uma única réplica e baixa concorrência, mas impede alta disponibilidade e escala horizontal. Também torna backup, restauração e retenção responsabilidades explícitas da operação Kubernetes. O processo atual inicia migrações leves automaticamente ao subir; qualquer alteração futura de esquema deve ser revisada com backup validado antes do deploy.

O endpoint será público quando o DNS apontar para o Ingress. Por isso, os controles de aplicação não podem pressupor que a rede interna é uma barreira de segurança. Caso o objetivo seja acesso apenas hospitalar, deve-se aplicar restrição de rede no Ingress/WAF/VPN antes da publicação.

## Ordem recomendada antes do deploy público

1. Corrigir os quatro achados críticos/altos de autorização e QR Code.
2. Remover defaults de credenciais e chave de sessão; criar Secrets fortes somente no cluster.
3. Auditar o arquivo SQLite rastreado e remover quaisquer dados reais do Git, com rotação do token QR quando aplicável.
4. Implementar CSRF e auditoria de ações administrativas.
5. Configurar varredura de dependências e imagem; revisar resultados antes de publicar.
6. Definir backup testado para o PVC SQLite e procedimento de restauração.
7. Só então enviar a imagem ao ECR e aplicar os manifests no EKS.

## Decisão de deploy

**Não recomendado para exposição pública no estado atual.** É aceitável continuar com a preparação técnica de imagem e infraestrutura sem tornar o Ingress acessível externamente, mas o deploy produtivo deve aguardar a correção e validação dos itens críticos e altos.
