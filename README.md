# Hospital Rio Grande — Chamador de Enfermagem

Sistema de chamados de enfermagem, 100% focado em atendimento de pacientes
internados, com encaminhamento automático para a Central de Hotelaria
quando a solicitação não é de natureza clínica.

O projeto hospeda **dois sistemas independentes em um único processo
Flask**:

| Sistema | Blueprints | Prefixo de URL | Propósito |
|---|---|---|---|
| **Chamador de Enfermagem** (novo/reescrito) | `enfermagem_pages`, `enfermagem_api` | `/enfermagem`, `/api/enfermagem` | Chamados clínicos: urgência, dor, soro, falar com enfermagem |
| **Central de Hotelaria** (sistema já existente, preservado) | `hotelaria_pages`, `hotelaria_api` | `/hotelaria`, `/hotelaria/api` | Solicitações não clínicas: acomodação, alimentação, lavanderia, manutenção, higienização |
| **Portal** | `portal` | `/` | Tela inicial com as 2 entradas administrativas (Admin Enfermagem / Admin Hotelaria) |

Eles compartilham apenas o processo e o arquivo de banco de dados — cada um
tem suas próprias tabelas, rotas e telas. A única ponte entre os dois é a
categoria **"Outros"** do fluxo de paciente da Enfermagem, que cria o
chamado diretamente na Hotelaria (ver seção *Encaminhamento "Outros" →
Hotelaria*).

## Como executar

```bash
pip install -r requirements.txt
python app.py
```

A aplicação sobe em `http://localhost:5000` (porta configurável via
variável de ambiente `PORT`). Não há passo de "criar banco" separado: na
primeira execução, `db.py` cria o arquivo SQLite e todas as tabelas
automaticamente.

Login de teste da Central de Hotelaria: `admin` / `12345` (variáveis de
ambiente `HOTELARIA_USUARIO` / `HOTELARIA_SENHA` para trocar em produção).

Login de teste da área administrativa do Chamador de Enfermagem:
`enfermagem` / `12345` (variáveis de ambiente `ENFERMAGEM_USUARIO` /
`ENFERMAGEM_SENHA` para trocar em produção).

## Arquitetura técnica

- **Flask puro + `sqlite3` da biblioteca padrão — sem ORM.** Não há
  Flask-SQLAlchemy nem Flask-SocketIO no projeto final. Essa foi uma
  decisão deliberada: o ambiente onde o sistema foi construído e testado
  não tinha acesso à internet para instalar essas dependências, e a
  prioridade do projeto era ter um sistema **realmente testado e
  verificado**, não apenas escrito. `sqlite3` + `PRAGMA journal_mode=WAL`
  entrega concorrência real (múltiplos leitores/gravadores simultâneos)
  sem exigir um servidor de banco externo, o que é adequado ao porte de
  um único hospital rodando em uma máquina local.
- **Atualização em tempo real via polling**, não WebSocket. Cada tela
  (central de enfermagem, tela de acompanhamento do paciente, chat da
  hotelaria) busca o estado atual a cada 4–5 segundos.
  Isso é suficiente para o caso de uso (chamados de enfermagem não exigem
  latência de milissegundos) e elimina a dependência de
  Flask-SocketIO/eventlet, tornando o deploy mais simples (qualquer
  servidor WSGI comum serve o projeto, sem precisar de suporte a
  WebSocket).
- **Sem ORM, mas com uma camada fina de modelo.** `enfermagem/models.py`
  define `ChamadoEnfermagem`, uma classe leve que envolve uma
  `sqlite3.Row` e expõe os campos de data já convertidos em `datetime` —
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

1. `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=8000` em toda conexão
   SQLite — permite leitores e gravadores concorrentes sem erros de
   "database is locked".
2. **Transições de status atômicas**: "assumir" e "finalizar" um chamado
   são feitos com `UPDATE ... WHERE id = ? AND status = ?` e checagem de
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

**Chamador de Enfermagem** (`/enfermagem`, `/api/enfermagem`)
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

## O que foi mantido, removido e reescrito

- **Mantido**: a estrutura de blueprints do Flask, o conceito de
  identificação por leito, o layout de duas colunas do painel
  administrativo, e todo o sistema de Hotelaria (arquivo 2) — que
  continua funcionando exatamente como antes, apenas com um pequeno
  campo `origem` adicionado.
- **Removido**: Flask-SQLAlchemy, Flask-SocketIO/eventlet, qualquer
  referência a nome de paciente, e todo o conteúdo/estilo de hotelaria
  que antes estava misturado na tela de enfermagem.
- **Reescrito por completo**: o fluxo de chamado do paciente (agora em 2
  passos simples, 5 categorias fixas na ordem exigida), o algoritmo de
  priorização (antes inexistente/baseado só em horário), o dashboard de
  TV (agora sem rolagem, com sistema de densidade adaptável), o painel de
  enfermagem (filtros, chips de prioridade, modal de ação) e todo o
  design visual (`static/css/enfermagem.css`), com um sistema de cores
  por prioridade e tipografia pensada para leitura à distância na TV.

## Correção: chamado "desaparecendo" ao atualizar a página

O fluxo do paciente (`/enfermagem/`) é uma página única (SPA): da seleção
de leito até a confirmação de envio, a URL do navegador nunca muda. Se o
paciente atualizasse a página (F5) — ou a aba fosse recarregada por
qualquer motivo — **depois** de enviar o chamado mas **antes** de clicar
em "Acompanhar chamado", o chamado continuava existindo normalmente no
banco de dados, mas a tela voltava ao passo 1 e o paciente não tinha mais
como saber o número do chamado para encontrá-lo. Corrigido salvando uma
referência (`id` + `leito`, nunca o conteúdo do chamado) no
`localStorage` do dispositivo assim que o chamado é criado — o mesmo
mecanismo que a Central de Hotelaria já usava. Ao carregar `/enfermagem/`,
o app agora verifica primeiro se há um chamado ativo salvo: se houver e
ele ainda não estiver finalizado, o paciente é levado direto para a tela
de acompanhamento; se já estiver finalizado (ou não existir mais), a
referência é descartada e o fluxo normal de um novo chamado é exibido.
Isso também evita, como efeito colateral desejado, que o mesmo dispositivo
abra vários chamados simultâneos sem perceber que já tem um em
andamento.

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

## Alterações — identidade visual da Hotelaria, login e ajustes de fluxo

Rodada de mudanças pontuais pedida pelo usuário, sem alterar nenhuma
funcionalidade já testada e em funcionamento:

- **"Falar com Enfermagem" sem etapa de "Detalhar".** Para essa
  categoria específica, o chamado é criado assim que o paciente toca na
  subopção — sem campo de texto opcional e sem passo de confirmação. As
  outras 4 categorias (Urgência, Dor, Soro, Outros) continuam com o
  fluxo completo (detalhar → confirmar → enviar). Implementado em
  `renderPasso3()` (`static/js/enfermagem/paciente.js`), que agora
  ramifica o comportamento pelo nome da categoria.

- **Identidade visual do Chamador de Enfermagem copiada da Central de
  Hotelaria.** Paleta de cores, tipografia (Manrope), raio de borda,
  sombras, botões, cards, chips e o cabeçalho em degradê azul da tela do
  paciente agora usam exatamente os mesmos valores de
  `static/css/hotelaria.css`. As 4 faixas de prioridade (crítica/alta/
  média/baixa) — um conceito que a Hotelaria não tem — foram remontadas
  só com cores que já existem literalmente na paleta da Hotelaria
  (vermelho, amarelo, verde e um cinza-neutro para "média", escolhido
  para não se confundir com o azul de marca usado em botões e no status
  "em atendimento"). Aplicado em todas as rotas do sistema: paciente,
  acompanhamento, central, histórico, TV e a nova tela de login.

- **Logo do hospital removida do topo do Chamador de Enfermagem.** Todos
  os cabeçalhos (paciente, acompanhamento, central, histórico, TV,
  login) agora mostram só o nome em texto, sem a imagem da logo — o
  restante da identidade visual (cores, layout, tipografia) continua
  igual à da Hotelaria. A Central de Hotelaria e o portal inicial não
  foram alterados nesse ponto.

- **Login obrigatório para a área administrativa da Enfermagem.** Novas
  rotas `GET/POST /enfermagem/login` e `GET /enfermagem/logout`
  (`enfermagem/routes.py`), com sessão de servidor no mesmo padrão já
  usado pela Hotelaria (`enfermagem/auth.py`, decorator
  `login_requerido`). Credenciais de teste configuráveis por variável de
  ambiente (`ENFERMAGEM_USUARIO`/`ENFERMAGEM_SENHA`, padrão
  `enfermagem`/`12345` — ver `config.py`). Protegidos: as páginas
  `/enfermagem/dashboard`, `/enfermagem/central` e
  `/enfermagem/historico`, e
  os endpoints de API usados só pela equipe (`GET /chamados`,
  `GET /tv`, `GET /metricas`, `POST /.../assumir`,
  `POST /.../finalizar` — retornam 401 em JSON sem sessão). Os
  endpoints usados pelo paciente continuam 100% públicos, sem exigir
  login: criar chamado, consultar um chamado pelo ID (tela de
  acompanhamento) e avaliar.

- **Dashboard da TV refeito** para seguir a estrutura visual do
  Dashboard administrativo da Hotelaria (cabeçalho branco fixo, sem
  logo, cartões de resumo e painéis brancos com sombra suave), mantendo
  — sem alterar — a fila de atendimento ordenada por prioridade em
  tempo real e o comportamento sem rolagem já testado (limite de linhas
  visíveis + selo "+N aguardando", sistema de densidade adaptável). O
  conteúdo (fila de chamados individuais por leito/prioridade) foi
  mantido como está, já que os gráficos agregados da Hotelaria não
  fazem sentido para uma fila que precisa mostrar cada chamado
  individualmente.

Testado após as mudanças: acesso sem login às rotas/endpoints
administrativos (redireciona / 401), login com credencial errada, login
correto liberando todas as rotas protegidas, logout revogando o acesso
imediatamente, criação de chamado em todas as 5 categorias (incluindo o
novo fluxo direto de "Falar com Enfermagem" e o encaminhamento de
"Outros" para a Hotelaria, ambos continuando a funcionar), ciclo
assumir → finalizar → avaliar, e renderização de todas as páginas do
sistema. A Central de Hotelaria foi conferida à parte e continua
funcionando sem nenhuma alteração de comportamento.

## Alterações — banner de status na tela de acompanhamento

Pedido do usuário: a tela de acompanhamento do paciente já trocava de
estado (via `GET /api/enfermagem/chamados/<id>`, atualizado por polling
a cada 5s) quando o chamado era assumido, colocado em atendimento e
finalizado, mas isso só aparecia na trilha de progresso — pouco visível.
Adicionado um banner grande e explícito no topo da tela
(`static/js/enfermagem/acompanhar.js`, `static/css/enfermagem.css`) com
ícone, título e mensagem específicos para cada status:

- 🕐 **Aguardando enfermagem** (pendente)
- 🩺 **Chamado assumido — em atendimento** (mostra o nome do
  profissional responsável)
- ✅ **Atendimento finalizado**

A trilha de progresso (Recebido → Aguardando → Em atendimento →
Finalizado) e o restante da tela continuam iguais. Testado o ciclo
completo via API (criar → assumir → finalizar) confirmando que cada
transição de status é refletida corretamente nos dados que a tela
consome.

## Alterações — remoção do Dashboard de TV, filtros no Dashboard, portal e avaliação da Hotelaria

Rodada de ajustes pontuais, sem alterar nenhuma funcionalidade já
testada e em funcionamento além do que está descrito abaixo:

- **Dashboard de TV removido.** Rota `GET /enfermagem/tv`, template
  `templates/enfermagem/tv.html` e `static/js/enfermagem/tv.js`
  excluídos, junto com o link "Dashboard TV ↗" do menu administrativo
  (Dashboard/Central/Histórico). O endpoint `GET /api/enfermagem/tv`
  **foi mantido** — ele também alimenta os cartões de status da Central
  (`central.js`), então removê-lo quebraria uma tela em uso.
- **Link "Portal" removido do menu do Chamador de Enfermagem** (Dashboard/
  Central/Histórico), já que o botão "Sair" cobre a mesma necessidade de
  deixar a área administrativa.
- **Filtros funcionais no Dashboard de Enfermagem.** Adicionado o mesmo
  painel de filtros (status, prioridade, andar, tipo de solicitação,
  período) já usado no Histórico, agora também em
  `templates/enfermagem/dashboard.html`. O endpoint
  `GET /api/enfermagem/metricas` passou a aceitar os mesmos parâmetros de
  filtro de `GET /api/enfermagem/chamados`, e `static/js/enfermagem/
  dashboard.js` reenvia os cartões e gráficos a cada mudança de filtro.
- **Portal inicial (`/`) com o design antigo.** O visual voltou a ser o
  do portal original do projeto (fundo claro em degradê radial, caixa
  central com wordmark, cartões com ícone quadrado e link "Acessar →" —
  regras hoje reescritas em `static/css/enfermagem.css`, no lugar do
  fundo em degradê azul/verde escuro usado antes). As 3 entradas
  continuam as mesmas em uso hoje (Paciente / Admin Enfermagem / Admin
  Hotelaria) — só o estilo mudou.
- **Tela de confirmação de resolução removida do paciente da Hotelaria.**
  A pergunta "O problema foi resolvido?" (com "Problema resolvido" /
  "Não resolvido") não aparece mais na tela de acompanhamento
  (`static/js/hotelaria/paciente.js`). O campo/endpoint
  `confirmacao_resolucao` no backend foi mantido intacto (continua
  visível para a Central em `central.js`/`historico.js` e a expiração
  automática após 30 minutos continua rodando) — só a etapa que pedia
  essa confirmação ao paciente foi retirada.
- **Botão "Sair sem avaliar" na avaliação da Hotelaria.** Ao lado de
  "Enviar avaliação", o paciente agora pode encerrar o acompanhamento
  sem avaliar; isso apenas limpa a referência local (`localStorage`) do
  chamado ativo no dispositivo e volta à tela inicial — o chamado em si
  permanece salvo normalmente no servidor.

## Alterações — logos, remoção do chat do paciente, filtros da Hotelaria e unificação visual dos dois sistemas

- **Logos atualizadas.** `static/img/logo-icon.png` e
  `static/img/logo-horizontal.png` (versões "mestre", com fundo opaco)
  foram substituídas pelas novas logos enviadas pelo usuário. A partir
  delas foram geradas por chroma-key as versões de fundo transparente já
  usadas no resto do sistema: `hotelaria-logo-icon.png`,
  `hotelaria-logo-wordmark.png` e `favicon.png`. O logo antigo não usado
  em nenhuma tela (`logo-rg.png`, lettermark "RG") foi removido.
- **"Fale com a Central" removido do paciente da Hotelaria.** O painel de
  chat que aparecia na tela de acompanhamento do paciente
  (`static/js/hotelaria/paciente.js`) foi retirado, junto com o código
  só usado por ele (`bolhaMensagem`, `enviarMensagemChat`,
  `adicionarNovasMensagens`). A conversa "Conversa com o paciente" do
  lado da equipe (Central, `central.js`) **não foi alterada** — é uma
  implementação própria, independente da do paciente; a equipe continua
  podendo enviar mensagens normalmente, só o paciente deixou de vê-las
  ou responder por ali.
- **Filtros no Dashboard da Hotelaria.** Mesmo padrão já usado na
  Central/Histórico (filtro por serviço) mais status e período, agora
  também em `templates/hotelaria/dashboard.html`. O endpoint
  `GET /hotelaria/api/dashboard/resumo` passou a aceitar `servico`,
  `status` e `periodo`.
- **Design do Chamador de Enfermagem e da Central de Hotelaria
  unificado.** Foi corrigida uma inconsistência visual: as telas do
  Chamador de Enfermagem (login, dashboard, central, histórico) usavam a
  versão **opaca** da logo (com um leve "halo" cinza visível atrás do
  ícone), enquanto a Hotelaria já usava a versão transparente — agora
  ambas usam a mesma logo transparente. O cabeçalho administrativo
  (`.topo-admin`/`.marca-admin`/`.titulos-admin`/`.nav-admin`, em
  `static/css/enfermagem.css`) também foi ajustado para usar exatamente
  os mesmos valores de tipografia, cor e espaçamento do cabeçalho da
  Hotelaria (`.topo`/`.marca`/`.subtitulo`, em
  `static/css/hotelaria.css`) — título em azul e peso 800, subtítulo
  em caixa alta com letter-spacing, mesmo hover/estado ativo do menu.
  O texto de cada tela continua específico de cada sistema (ex.: título
  da página numa e nome da marca na outra) — só o estilo virou idêntico.

## Remasterização — auditoria completa, dashboards ultra e endurecimento (2026)

Rodada ampla de remasterização mantendo 100% a stack (Flask + SQLite puro +
Jinja + JS vanilla, sem build step). Nada foi migrado para outro framework;
tudo abaixo é evolução sobre a base já existente.

**Fundação compartilhada (nova, elimina duplicação):**
- `andares.py` — Andares/leitos, antes só da Enfermagem, agora compartilhado
  também pela Hotelaria.
- `ratelimit.py` — limitador de tentativas de login em memória.
- `timeutils.py` ganhou `limite_periodo`, `janela_comparativa_anterior`,
  `agrupar_por_dia`, `agrupar_por_hora` — substituem cópias quase idênticas
  que existiam em `enfermagem/api.py` e `hotelaria/routes.py`.
- `static/css/base.css` (novo) — tokens de design, botões, selos, cabeçalho
  admin, cartões/gráficos de dashboard, filtros, modal, login, portal, toast.
  `enfermagem.css` e `hotelaria.css` agora só têm o que é específico de cada
  módulo e importam este arquivo.
- `static/js/common.js` (novo, `window.HRG`) — `escapeHtml`, `formatarMinutos`,
  `toast` (substitui todos os `alert()`), `fetchJSON` (timeout + erro
  legível), `pollWhileVisible` (pausa polling com a aba oculta, sem
  requisições sobrepostas), detector de mudança (evita re-render/flicker).

**Segurança:**
- `debug=False` por padrão (`FLASK_DEBUG=1` para depurar localmente) — antes
  ficava sempre ligado, expondo stack trace completo em qualquer erro.
- Cabeçalhos de segurança (`X-Content-Type-Options`, `X-Frame-Options`,
  `Content-Security-Policy`, `Referrer-Policy`), cookie de sessão com
  `HttpOnly`/`SameSite=Lax`/`Secure` (opcional via env), limite de tamanho de
  requisição, limites de caracteres em todo campo de texto livre.
- Handler de erro genérico: qualquer exceção inesperada vira uma tela/JSON
  neutro para o usuário e vai para o log do servidor — nunca mais um stack
  trace na tela.
- Login da Enfermagem e da Hotelaria protegidos por limitador de tentativas.

**Enfermagem — "Assumir chamado" sem nome digitado:** o responsável é
sempre o usuário logado na sessão (não um campo de texto livre); a etapa de
digitar o nome foi removida — "Assumir" virou um clique único. O nome não é
mostrado em nenhuma tela (permanece só como registro interno).

**Hotelaria — leito por Andar → Leito:** o paciente da Hotelaria agora
escolhe o leito no mesmo seletor Andar → Leito da Enfermagem (antes era
texto livre, sem validação). Nova coluna `andar` em `hotelaria_chamados`
(migração automática, não perde dados existentes) habilita o gráfico
"Chamados por andar" no dashboard. O selo "🩺 Encaminhado pela Enfermagem"
foi removido dos cartões da Central/Histórico (o contador agregado
"Encaminhados pela Enfermagem" do dashboard continua existindo).

**Dashboards ultra-avançados (dados sempre reais, nada inventado):** taxa de
finalização, chamados críticos/acima do tempo esperado (nova meta de SLA por
prioridade em `enfermagem/priority.py`), chamado pendente mais antigo,
comparativo com o período anterior equivalente (só quando há um período
definido), demanda por hora do dia, distribuição por andar (Hotelaria).
Painel "Atenção imediata" na Central de Enfermagem, reaproveitando dados já
carregados. Filtros novos: busca livre, ordenação, intervalo de datas,
andar (Hotelaria); chips de filtros ativos com remoção individual.

**Confiabilidade:** criação de chamado deduplicada no backend (não só no
JS) — duplo clique/retry de rede devolve o chamado já existente em vez de
duplicar. Listagens têm paginação opcional (`limite`/`offset` +
`X-Total-Count`, retrocompatível) e um teto de segurança para não crescer
sem limite; histórico usa "carregar mais". Polling pausa com a aba oculta e
nunca sobrepõe requisições.

**Mobile-first e acessibilidade:** breakpoints mais finos entre 320–430px,
alvo de toque mínimo de 44px, quadro Kanban da Hotelaria vira abas em telas
estreitas, `<label for=”...”>` corrigido em todos os filtros, `aria-label`
em botões só-ícone, modais com `role="dialog"`, fechamento com Esc,
`:focus-visible` visível em toda a interface, contraste das faixas de
prioridade ajustado para AA.

Testado de ponta a ponta (API + navegador, mobile e desktop) após as
mudanças: criação de chamados nas 5 categorias da Enfermagem e nos 5
serviços da Hotelaria, ciclo completo assumir/andamento → finalizar →
avaliar, guarda de duplicidade, login com limite de tentativas, dashboards
e filtros com dados reais, e ausência de qualquer stack trace exposta.

## Alterações — dados de demonstração e ordem do Soro

- **Soro:** "Problema no acesso" agora vem antes de "Acabou" na tela do
  paciente (ordem definida em `enfermagem/constants.py`).
- **Dados fictícios de demonstração** (`dados_demo.py`): ~60 dias de
  histórico + chamados ativos "de agora" nos dois módulos (prioridades,
  status, tempos, avaliações, comentários, mensagens, encaminhamentos).
  Inseridos automaticamente na inicialização **somente se o banco não tiver
  nenhum chamado** — nunca apagam nada. `DADOS_DEMO=0` desliga.
  `python dados_demo.py --ativos` acrescenta um novo lote de chamados ativos.

## Alterações — Dashboard por período, Central e ajustes do paciente

- **Ícone de Limpeza** trocado por uma vassoura (Enfermagem › Outros e tela
  do paciente da Hotelaria; chave `limpeza` em `hotelaria/models.py`).
- **Falar com Enfermagem:** o paciente marca o assunto e confirma no botão
  **Selecionar** (antes o chamado era enviado no primeiro toque). Continua
  sem a tela de resumo.
- **Dashboard de Enfermagem:** seletor fixo **Hoje | Últimos 7 dias |
  Últimos 30 dias | Tudo**. "Chamados por período" muda o agrupamento
  conforme o filtro: Hoje = últimas 24 horas por hora; 7 dias = por dia;
  30 dias = por semana; Tudo = por mês (`serie_periodo` em
  `GET /api/enfermagem/metricas`). Novo gráfico **Chamados por andar**,
  separado por prioridade (`por_andar_prioridade`).
- **Central de Enfermagem:** fila ordenada por faixa (Crítico → Médio →
  Baixo) e, dentro da faixa, por maior tempo de espera.
- **Centrais (Enfermagem e Hotelaria):** ao finalizar um chamado, o detalhe
  fecha automaticamente (também quando outra pessoa finaliza enquanto ele
  está aberto).

## Alterações — paleta azul dos dashboards e Dashboard da Hotelaria no mesmo sistema

- **Paleta dos gráficos** (`--grafico-1` … `--grafico-5` em `static/css/base.css`):
  escala de azuis derivada da cor de marca, do azul-marinho ao azul-claro,
  combinando com o branco e o azul do hospital. Prioridade e status seguem a
  intensidade: Crítico/Pendente = mais escuro, Médio/Em andamento = azul da
  marca, Baixo/Finalizado = azul-claro. Selo de tendência dos cartões em
  tons de azul.
- **Sistema de dashboard compartilhado** (`static/js/dashboard_comum.js`):
  cartões, barras, "Chamados por período", "Chamados por andar" (empilhado),
  seletor de período e chips de filtro usados pelos dois dashboards. A série
  por período também é compartilhada (`timeutils.serie_periodo`).
- **Dashboard da Hotelaria** agora igual ao da Enfermagem: seletor Hoje |
  Últimos 7 dias | Últimos 30 dias | Tudo (24h por hora / dia / semana / mês),
  filtros avançados (busca, serviço, status, andar, De/Até), gráficos por
  serviço, por status, por período e por andar (separado por status).
  `GET /hotelaria/api/dashboard/resumo` ganhou `data_inicio`/`data_fim`,
  `serie_periodo` e `por_andar_status`.

## Alterações — meta de 30 min na Hotelaria e acompanhamento padronizado

- **Meta de espera de 30 minutos em todos os chamados da Hotelaria**
  (`hotelaria/models.py::META_ESPERA_MIN`), no mesmo modelo das metas da
  Enfermagem: cada chamado traz `tempo_espera_min`, `sla_min` e
  `acima_do_tempo_esperado`. Na Central da Hotelaria, os cartões mostram o
  selo "⏱ tempo / meta 30min" (normal, alerta a partir de 70% da meta,
  vermelho acima da meta), o detalhe mostra o tempo de espera e o selo
  "Acima do tempo esperado", há o novo contador "Acima do tempo esperado" e,
  dentro de pendentes/em andamento, quem espera há mais tempo vem primeiro.
- **Tela de acompanhamento da Enfermagem igual à da Hotelaria**: cabeçalho
  com título e trilha, selo de status, trilha Recebido → Em atendimento →
  Finalizado, resumo em caixa e avaliação no mesmo formato ("Sair sem
  avaliar" como botão). Os estilos dessa tela agora ficam em `base.css`,
  compartilhados pelos dois módulos. Corrigido também o "Sair sem avaliar",
  que levava para um endereço inexistente (`/enfermagem/paciente`).

## Alterações — fim da área do paciente da Hotelaria

- A tela `/hotelaria/paciente` (e o fluxo próprio de abertura de chamado da
  Hotelaria) foi removida; o paciente usa só a área do paciente da
  Enfermagem (`/enfermagem/`), e a categoria **Outros** continua enviando os
  pedidos para a Central de Hotelaria. Quem abrir o endereço antigo
  (`/hotelaria/paciente`, links ou QR codes já impressos) é levado para
  `/enfermagem/`.
- O acompanhamento de um pedido de Hotelaria agora é
  `/enfermagem/acompanhar-hotelaria/<id>` (`templates/enfermagem/acompanhar_hotelaria.html`,
  `static/js/hotelaria/acompanhar.js`), com o mesmo visual do acompanhamento
  da Enfermagem. **Sair sem avaliar** (e "Voltar ao início" depois de avaliar)
  volta para a área do paciente da Enfermagem, pronta para um novo chamado.
- A área do paciente da Enfermagem retoma sozinha um pedido de Hotelaria em
  aberto (ou finalizado e ainda sem avaliação) neste dispositivo.

## Alterações — acesso do paciente pelo QR Code válido até a meia-noite

- O QR Code de cada leito é **fixo** (o token nunca é trocado). O antigo
  botão "Revogar acesso de todos os links atuais" de Configurações, que
  gerava um token novo e invalidava os QR Codes impressos, foi removido.
- Ao escanear, o paciente entra sem senha: o servidor grava na sessão do
  navegador o leito e o horário (Fortaleza) e redireciona para `/enfermagem/`
  sem o token — recarregar a página não renova o acesso, só escanear.
- O acesso vale até a **próxima meia-noite (00:00, America/Fortaleza)** para
  todo mundo, não 24 h a partir do escaneamento. Depois disso, a tela do
  paciente e as de acompanhamento mostram "Acesso expirado — escaneie o QR
  Code do seu leito"; escaneando de novo, entra até a meia-noite seguinte.
- Configurações: o **Gerador de QR Code por Leito** fica no topo; **Controle de Leitos** e
  **Acesso pelo QR Code** ficam recolhidos e só aparecem ao clicar em "Mostrar".
- Configurações → **Acesso pelo QR Code** (com cronômetro de quanto falta para o reset da meia-noite): "Expirar acesso" por leito
  e "Expirar todos", ambos com confirmação ("Tem certeza?"), liberados para
  qualquer usuário logado na área administrativa (uso de teste). A tela aberta no celular troca para
  "Acesso expirado" em até ~10 s (`static/js/enfermagem/acesso_paciente.js`).
  Quem escanear depois da revogação entra, mas só até a mesma meia-noite.
- Regra em `enfermagem/acesso.py`; tabela `enfermagem_acesso_leitos` guarda
  só andar, leito e horários — nenhum dado do paciente.
