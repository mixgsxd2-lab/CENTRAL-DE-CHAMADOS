# Hospital Rio Grande — Central de Chamados

Sistema de chamados de enfermagem, focado em atendimento de pacientes
internados, com encaminhamento automático para a Central de Hotelaria
quando a solicitação não é de natureza clínica.

O projeto hospeda **dois sistemas independentes em um único processo
Flask**:

| Sistema | Blueprints | Prefixo de URL | Propósito |
|---|---|---|---|
| **Central de Chamados** (novo/reescrito) | `enfermagem_pages`, `enfermagem_api` | `/enfermagem`, `/api/enfermagem` | Chamados clínicos: urgência, dor, soro, falar com enfermagem |
| **Central de Hotelaria** (sistema já existente, preservado) | `hotelaria_pages`, `hotelaria_api` | `/hotelaria`, `/hotelaria/api` | Solicitações não clínicas: acomodação, alimentação, lavanderia, manutenção, higienização |
| **Portal** | `portal` | `/` | Tela inicial com as 2 entradas administrativas (Admin Enfermagem / Admin Hotelaria) |

Eles compartilham apenas o processo e o banco de dados MySQL — cada um
tem suas próprias tabelas, rotas e telas. A única ponte entre os dois é a
categoria **"Outros"** do fluxo de paciente da Enfermagem, que cria o
chamado diretamente na Hotelaria (ver seção *Encaminhamento "Outros" →
Hotelaria*).

## Como executar

```bash
pip install -r requirements.txt
cp .env.example .env   # ajuste host/usuário/senha do seu MySQL
python app.py
```

É preciso ter um MySQL acessível (local, em container ou gerenciado) antes
de subir a aplicação — veja `MYSQL_HOST`/`MYSQL_PORT`/`MYSQL_USER`/
`MYSQL_PASSWORD`/`MYSQL_DATABASE` em `config.py`. Com `docker compose up`,
um MySQL já é criado automaticamente (ver `docker-compose.yaml`). A
aplicação sobe em `http://localhost:5000` (porta configurável via
variável de ambiente `PORT`). O banco (`MYSQL_DATABASE`) precisa existir
no servidor; na primeira execução, `db.py` cria todas as tabelas
automaticamente.

## Arquitetura técnica

- **Flask puro + PyMySQL — sem ORM.** Não há Flask-SQLAlchemy nem
  Flask-SocketIO no projeto final. Essa foi uma decisão deliberada: a
  prioridade do projeto era ter um sistema **realmente testado e
  verificado**, não apenas escrito, com o mínimo de dependências. As
  consultas são SQL escrito à mão, com `%s` como marcador de parâmetro.
- **Atualização em tempo real via polling**, não WebSocket. Cada tela
  (central de enfermagem, tela de acompanhamento do paciente, chat da
  hotelaria) busca o estado atual a cada 4–5 segundos.
  Isso é suficiente para o caso de uso (chamados de enfermagem não exigem
  latência de milissegundos) e elimina a dependência de
  Flask-SocketIO/eventlet, tornando o deploy mais simples (qualquer
  servidor WSGI comum serve o projeto, sem precisar de suporte a
  WebSocket).
- **Sem ORM, mas com uma camada fina de modelo.** `enfermagem/models.py`
  define `ChamadoEnfermagem`, uma classe leve que envolve uma linha do
  banco (dicionário do `DictCursor`) e expõe os campos de data já convertidos em `datetime` —
  o suficiente para o restante do código (`priority.py`,
  `serializers.py`) trabalhar com atributos normais, sem reimplementar um
  ORM completo.
- **Fuso horário único e confiável**: todo carimbo de tempo usa
  `America/Fortaleza` (`timeutils.agora()`), nunca o relógio do
  dispositivo do paciente/admin — evita inconsistência de horário de
  espera entre dispositivos diferentes.

## Concorrência e segurança contra duplicidade

O requisito de suportar múltiplos pacientes e administradores
simultaneamente sem duplicar ou perder chamados foi resolvido com:

1. O MySQL/InnoDB suporta leitores e gravadores concorrentes de várias
   conexões/processos nativamente.
2. **Transições de status atômicas**: "assumir" e "finalizar" um chamado
   são feitos com `UPDATE ... WHERE id = %s AND status = %s` e checagem de
   `cursor.rowcount`. Se dois profissionais tentarem assumir o mesmo
   chamado ao mesmo tempo, apenas um `UPDATE` afeta uma linha — o outro
   recebe `rowcount == 0` e a API responde `409 Conflito`, sem duplicar
   nem sobrescrever o atendimento.
3. Testado sob carga real durante o desenvolvimento: 60 chamados criados
   por 30 threads simultâneas (0,22s, sem erros, sem IDs duplicados) e
   teste de corrida de "assumir" (dois profissionais, mesmo chamado — um
   recebe sucesso, o outro 409).

## Algoritmo de prioridade

A fila de atendimento **não é ordenada apenas por horário**. Cada
chamado recebe uma pontuação (`enfermagem/priority.py`), igual à
**gravidade base** (0–100) da subopção escolhida pelo paciente — ex.:
"Não consigo respirar bem" = 100, "Dor leve" = 25 — e mapeada em 3
níveis: 🔴 **Crítico** (gravidade ≥ 85, ou qualquer chamado de **Dor**), 🟡 **Médio** (≥ 40),
🟢 **Baixo** (abaixo disso). A fila do painel de enfermagem e da TV é
sempre ordenada por esses níveis (e, dentro do mesmo nível, pela
pontuação exata), não pela ordem de chegada.

Cada nível também tem uma meta de tempo de espera (SLA) até o início do
atendimento — Alta: 10 min, Média: 20 min, Baixa: 40 min — usada para
sinalizar chamados "acima do tempo esperado" nos dashboards e na Central,
mas que não altera o nível de criticidade do chamado.

## Encaminhamento "Outros" → Hotelaria

Ao escolher a categoria **"Outros"** na tela de "Como podemos ajudar?", o
paciente vê as mesmas 5 opções de serviço já existentes na Central de
Hotelaria (Acomodação, Alimentação, Lavanderia, Manutenção, Limpeza). A
API da Enfermagem (`enfermagem/api.py`) detecta essa categoria e, em vez
de criar um chamado de enfermagem, chama diretamente
`hotelaria.services.criar_chamado_hotelaria()` — o chamado nasce direto
na tabela e no fluxo da Hotelaria, marcado com `origem="enfermagem"` (a
Central de Hotelaria exibe um selo "🩺 Encaminhado pela Enfermagem" nesses
casos). O paciente é então levado para a própria tela de acompanhamento
da Hotelaria, que já sabe reabrir o chamado ativo automaticamente.

## Conformidade com LGPD

O paciente nunca é identificado por nome ou qualquer outro dado pessoal.
A única identificação usada em todo o sistema — na criação do chamado,
no banco de dados, no painel de enfermagem e na TV — é **andar + número
do leito**. Não existe campo de nome, CPF, prontuário ou qualquer dado
pessoal do paciente em nenhuma tabela.

## Estrutura do banco de dados

Tabelas principais (definidas em `db.py`, criadas automaticamente):

- **`enfermagem_chamados`**: `id`, `andar`, `leito`, `categoria`,
  `subcategoria`, `detalhe`, `gravidade_base`, `status`,
  `profissional_responsavel`, `criado_em`, `inicio_atendimento`,
  `finalizado_em`, `avaliacao`, `comentario_avaliacao`.
- **`hotelaria_chamados`**, **`hotelaria_mensagens`**,
  **`hotelaria_avaliacoes`**: preservadas do sistema de Hotelaria já
  existente, com a adição do campo `origem` (`"hotelaria"` ou
  `"enfermagem"`) para diferenciar chamados nativos de encaminhados.

Índices foram criados nas colunas mais consultadas (`status`, `leito`,
`criado_em`) para manter as consultas rápidas mesmo com muitos registros
históricos.

## Rotas principais

**Portal**
- `GET /` — tela inicial com as 3 entradas.

**Central de Chamados** (`/enfermagem`, `/api/enfermagem`)
- `GET /enfermagem/` — Passo 1/2 do paciente (andar/leito → tipo de
  solicitação).
- `GET /enfermagem/acompanhar/<id>` — acompanhamento do chamado pelo
  paciente.
- `GET /enfermagem/dashboard` — visão geral administrativa (filtros por
  status/prioridade/andar/categoria/período + cartões de métricas +
  gráficos por categoria/prioridade/período), no mesmo padrão visual do
  dashboard da Hotelaria.
- `GET /enfermagem/central` — painel da equipe de enfermagem (fila,
  filtros, assumir/finalizar).
- `GET /enfermagem/historico` — histórico com filtros avançados.
- `POST /api/enfermagem/chamados` — cria um chamado (ou encaminha para a
  Hotelaria, se categoria = "Outros").
- `GET /api/enfermagem/chamados` — lista filtrada (status, prioridade,
  andar, leito, categoria, período).
- `GET /api/enfermagem/chamados/<id>` — detalhe de um chamado.
- `POST /api/enfermagem/chamados/<id>/assumir` — enfermagem assume o
  chamado (transição atômica).
- `POST /api/enfermagem/chamados/<id>/finalizar` — finaliza o
  atendimento.
- `POST /api/enfermagem/chamados/<id>/avaliar` — avaliação opcional do
  paciente (1–5 estrelas, bloqueada após a primeira).
- `GET /api/enfermagem/tv` — payload agregado (fila ordenada por
  prioridade + contadores) usado pelos cartões de status da Central.
- `GET /api/enfermagem/metricas` — métricas agregadas (totais, tempos
  médios, avaliação média, distribuição por categoria/prioridade/andar/dia),
  filtráveis por status/prioridade/andar/categoria/período — usadas pelo
  histórico e pelo dashboard.
- `GET /api/enfermagem/opcoes` — metadados de andares/leitos/categorias
  para o front-end.

**Central de Hotelaria** (`/hotelaria`, `/hotelaria/api`) — sistema
preservado do projeto original, com pequenas adições (`origem`, contador
`encaminhados_enfermagem` no resumo do dashboard, endpoint de mensagens
via POST no lugar do antigo evento de WebSocket).

## Testes realizados

Durante o desenvolvimento, o sistema foi validado de ponta a ponta via
requisições HTTP reais (não apenas leitura de código):

- Criação de chamado em cada uma das 4 categorias clínicas e
  encaminhamento correto da categoria "Outros" para a Hotelaria.
- Cálculo e ordenação de prioridade por gravidade base.
- Fluxo completo `pendente → em_atendimento → finalizado`, com bloqueio
  de ações após finalização.
- Concorrência: 60 criações simultâneas (30 threads) e disputa de
  "assumir" entre dois profissionais no mesmo chamado.
- Filtros combinados (status + prioridade + andar + leito + categoria +
  período) na central e no histórico.
- Avaliação opcional do paciente, incluindo bloqueio de reavaliação
  (409).
- Dashboard de TV: contadores, fila ordenada por prioridade e
  comportamento de transbordo ("+N outros chamados aguardando") quando a
  fila excede o limite de linhas visíveis sem rolagem.
- Renderização de todas as páginas principais (portal, fluxo do
  paciente, acompanhamento, central, TV, histórico, login/central/
  dashboard/histórico da Hotelaria) e tratamento de erros 404/409 em
  JSON (API) e HTML (páginas).