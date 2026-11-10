-- ============================================================================
-- Central de Chamados — criação inicial do banco PostgreSQL
-- ============================================================================
--
-- Finalidade
--   Criar o usuário dedicado, o banco lógico e as tabelas/índices usados pela
--   aplicação Central de Chamados (módulos Enfermagem e Hotelaria).
--
-- Compatibilidade
--   Este arquivo foi preparado para ser executado pelo cliente psql. Ele
--   contém comandos especiais do psql (linhas iniciadas por barra invertida),
--   além de SQL. Não execute este arquivo diretamente no Query Editor do
--   console AWS nem em um cliente que não interprete comandos do psql.
--
-- Como executar
--   1. Instale/abra o psql em uma estação autorizada a acessar o RDS.
--   2. Substitua <ENDPOINT_RDS> e <USUARIO_ADMIN_RDS> no comando abaixo.
--   3. Execute o comando no terminal. O psql solicitará as senhas nos momentos
--      apropriados; não coloque senhas na linha de comando nem neste arquivo.
--
--   psql -h <ENDPOINT_RDS> -p 5432 -U <USUARIO_ADMIN_RDS> -d postgres -f CRIAR_BANCO_CENTRAL_CHAMADOS.sql
--
-- Atenção
--   * Use apenas para a criação inicial, em ambiente aprovado pelo gestor.
--   * O script cria os nomes central_chamados e central_chamados_app. Se um
--     deles já existir, o script para no erro; não apague recursos existentes
--     para contornar isso. Peça ao DBA para verificar o estado primeiro.
--   * O banco começa vazio. Não há importação dos dados antigos de SQLite.
--   * A aplicação também cria tabelas/índices ao iniciar. A execução manual é
--     opcional; se escolhida, deve ser antes do deploy da nova imagem.
--   * O usuário central_chamados_app é dono do banco e cria as tabelas. Não é
--     usuário administrador do RDS e não recebe SUPERUSER.
--   * O usuário e a senha da aplicação devem ser guardados no mecanismo de
--     segredos aprovado pela equipe e enviados ao Kubernetes sem expô-los.
--   * O schema public é usado porque as consultas da aplicação não qualificam
--     os nomes das tabelas com outro schema.
--
-- Conectividade necessária para a aplicação
--   O endpoint deve ser privado e acessível a partir do EKS por rota de rede.
--   No Security Group do RDS, liberar somente TCP 5432 a partir do Security
--   Group/origem de workload definido pela equipe de plataforma. Não abrir o
--   banco para a internet. Confirmar VPC, sub-redes, rotas e origem autorizada
--   com o responsável pelo EKS; este arquivo não altera rede ou Security Groups.
--
-- TLS
--   O código atual usa psycopg2 sem definir explicitamente sslmode. Para uso
--   em produção, a aplicação deve ser configurada para exigir TLS e validar o
--   certificado do RDS (por exemplo, PGSSLMODE=verify-full e o CA oficial do
--   RDS em PGSSLROOTCERT). A criação deste banco não faz essa alteração no app.
--
-- ============================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- Fase 1: conectada inicialmente ao banco postgres como administrador do RDS.
-- Cria uma role de login sem privilégios administrativos. O comando psql
-- \password solicita a senha interativamente, sem gravá-la neste arquivo.
-- ---------------------------------------------------------------------------
CREATE ROLE central_chamados_app LOGIN;
\password central_chamados_app

-- CREATE DATABASE não pode ser executado dentro de uma transação. O psql
-- executa este arquivo sem envolver automaticamente todas as instruções em
-- uma única transação.
CREATE DATABASE central_chamados
    OWNER central_chamados_app
    ENCODING 'UTF8';

-- Reconecta ao banco novo usando a role da aplicação para que as tabelas,
-- índices e sequências criados abaixo pertençam à aplicação. O psql solicitará
-- a senha central_chamados_app se ela não estiver disponível por mecanismo
-- seguro de autenticação local.
\connect central_chamados central_chamados_app

-- ---------------------------------------------------------------------------
-- Fase 2: estrutura do módulo Enfermagem.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS enfermagem_chamados (
    id SERIAL PRIMARY KEY,
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    categoria VARCHAR(100) NOT NULL,
    subcategoria VARCHAR(100) NOT NULL,
    detalhe TEXT,
    gravidade_base INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'pendente',
    profissional_responsavel VARCHAR(255),
    criado_em VARCHAR(50) NOT NULL,
    inicio_atendimento VARCHAR(50),
    finalizado_em VARCHAR(50),
    avaliacao INT,
    comentario_avaliacao TEXT
);

CREATE INDEX IF NOT EXISTS idx_enf_status
    ON enfermagem_chamados (status);
CREATE INDEX IF NOT EXISTS idx_enf_leito
    ON enfermagem_chamados (leito);
CREATE INDEX IF NOT EXISTS idx_enf_criado_em
    ON enfermagem_chamados (criado_em);

CREATE TABLE IF NOT EXISTS enfermagem_leitos_inativos (
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    desde VARCHAR(50) NOT NULL,
    PRIMARY KEY (andar, leito)
);

CREATE TABLE IF NOT EXISTS enfermagem_config (
    chave VARCHAR(191) PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enfermagem_acesso_leitos (
    andar VARCHAR(100) NOT NULL,
    leito VARCHAR(100) NOT NULL,
    ultimo_acesso_em VARCHAR(50),
    expirado_em VARCHAR(50),
    PRIMARY KEY (andar, leito)
);

-- ---------------------------------------------------------------------------
-- Fase 3: estrutura do módulo Hotelaria.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS hotelaria_chamados (
    id SERIAL PRIMARY KEY,
    leito VARCHAR(100) NOT NULL,
    servico VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pendente',
    origem VARCHAR(50) NOT NULL DEFAULT 'hotelaria',
    criado_em VARCHAR(50) NOT NULL,
    iniciado_em VARCHAR(50),
    finalizado_em VARCHAR(50),
    confirmacao_resolucao VARCHAR(50) NOT NULL DEFAULT 'nao_aplicavel',
    prazo_confirmacao VARCHAR(50),
    andar VARCHAR(100)
);

-- A aplicação também possui esta migração idempotente para instalações em que
-- a tabela existia antes da coluna andar ser adicionada.
ALTER TABLE hotelaria_chamados
    ADD COLUMN IF NOT EXISTS andar VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_hotel_status
    ON hotelaria_chamados (status);
CREATE INDEX IF NOT EXISTS idx_hotel_leito
    ON hotelaria_chamados (leito);
CREATE INDEX IF NOT EXISTS idx_hotel_criado_em
    ON hotelaria_chamados (criado_em);

CREATE TABLE IF NOT EXISTS hotelaria_mensagens (
    id SERIAL PRIMARY KEY,
    chamado_id INT NOT NULL
        REFERENCES hotelaria_chamados (id) ON DELETE CASCADE,
    remetente VARCHAR(100) NOT NULL,
    mensagem TEXT NOT NULL,
    criado_em VARCHAR(50) NOT NULL,
    lida_central INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_hotel_msg_chamado
    ON hotelaria_mensagens (chamado_id);

CREATE TABLE IF NOT EXISTS hotelaria_avaliacoes (
    id SERIAL PRIMARY KEY,
    chamado_id INT NOT NULL UNIQUE
        REFERENCES hotelaria_chamados (id) ON DELETE CASCADE,
    estrelas INT NOT NULL,
    comentario TEXT,
    criado_em VARCHAR(50) NOT NULL
);

-- ---------------------------------------------------------------------------
-- Verificação final. A saída lista as tabelas do schema public.
-- ---------------------------------------------------------------------------
\dt public.*

-- Fim. Este arquivo contém apenas estrutura; não insere dados de produção.
