(function () {
  "use strict";

  // Mesmo sistema de dashboard da Enfermagem (static/js/enfermagem/dashboard.js):
  // gráficos, cartões, seletor de período e chips de filtro vêm de
  // static/js/dashboard_comum.js. Aqui só mudam os dados e os rótulos — a
  // Hotelaria não tem faixa de prioridade, então as quebras são por status.
  const D = HRGDashboard;
  const P = D.PALETA;
  const formatarMinutos = HRG.formatarMinutos;

  const FAIXAS_STATUS = [
    { chave: "pendente", rotulo: "Pendente", cor: P[0], rodape: ["pendente", "pendentes"] },
    { chave: "em_andamento", rotulo: "Em andamento" },
    { chave: "finalizado", rotulo: "Finalizado" },
  ];

  const filtros = {};
  const filtroBusca = document.getElementById("filtroBusca");
  const filtroServico = document.getElementById("filtroServico");
  const filtroStatus = document.getElementById("filtroStatus");
  const filtroAndar = document.getElementById("filtroAndar");
  const filtroDataInicio = document.getElementById("filtroDataInicio");
  const filtroDataFim = document.getElementById("filtroDataFim");
  const filtrosAtivosEl = document.getElementById("filtrosAtivos");

  D.ligarPainelFiltros(document.getElementById("botaoFiltrosAvancados"), document.getElementById("painelFiltrosAvancados"));
  document.getElementById("legendaAndar").innerHTML = D.legendaHtml(FAIXAS_STATUS);

  const TODOS_OS_CAMPOS = [filtroBusca, filtroServico, filtroStatus, filtroAndar, filtroDataInicio, filtroDataFim];

  async function carregar() {
    const params = new URLSearchParams();
    Object.entries(filtros).forEach(([chave, valor]) => { if (valor) params.set(chave, valor); });

    try {
      const { dados } = await HRG.fetchJSON(`/hotelaria/api/dashboard/resumo?${params.toString()}`);
      renderCartoes(dados);
      D.renderBarras(document.getElementById("graficoServico"),
        Object.entries(dados.por_servico || {}).map(([rotulo, valor]) => ({ rotulo, valor })));
      D.renderBarras(document.getElementById("graficoStatus"),
        FAIXAS_STATUS.map((fx) => ({ rotulo: fx.rotulo, valor: (dados.por_status || {})[fx.chave] || 0, cor: fx.cor })));
      D.renderPeriodo(document.getElementById("graficoPeriodo"), document.getElementById("subtituloPeriodo"), dados.serie_periodo);
      D.renderEmpilhado(document.getElementById("graficoAndar"), dados.por_andar_status, FAIXAS_STATUS, "pendente");
      if (dados.chamados_sem_andar) {
        document.getElementById("graficoAndar").insertAdjacentHTML("beforeend",
          `<p class="texto-suave" style="font-size:0.76rem; margin-top:8px;">+ ${dados.chamados_sem_andar} chamado(s) antigo(s) sem andar registrado.</p>`);
      }
    } catch (e) {
      HRG.toast("Não foi possível atualizar o dashboard.", "erro");
    }
  }

  function renderCartoes(d) {
    D.renderCartoes(document.getElementById("cartoesResumo"), [
      { rotulo: "Total de chamados", valor: d.total, destaque: true, extra: D.tendenciaHtml(d.comparativo_periodo_anterior) },
      { rotulo: "Pendentes", valor: d.pendentes },
      { rotulo: "Em andamento", valor: d.andamento },
      { rotulo: "Finalizados", valor: d.finalizados },
      { rotulo: "Tempo médio de espera", valor: formatarMinutos(d.tempo_medio_espera_min) },
      { rotulo: "Tempo médio de atendimento", valor: formatarMinutos(d.tempo_medio_atendimento_min) },
    ]);
  }

  // ---------------------------------------------------------------------
  // Filtros
  // ---------------------------------------------------------------------
  function renderFiltrosAtivos() {
    D.renderFiltrosAtivos(filtrosAtivosEl, [
      { chave: "q", el: filtroBusca, rotulo: (v) => `Busca: "${v}"` },
      { chave: "servico", el: filtroServico, rotulo: () => `Serviço: ${filtroServico.selectedOptions[0].textContent}` },
      { chave: "status", el: filtroStatus, rotulo: () => `Status: ${filtroStatus.selectedOptions[0].textContent}` },
      { chave: "andar", el: filtroAndar, rotulo: (v) => `Andar: ${v}` },
      { chave: "data_inicio", el: filtroDataInicio, rotulo: (v) => `De ${v}` },
      { chave: "data_fim", el: filtroDataFim, rotulo: (v) => `Até ${v}` },
    ], (chave) => {
      delete filtros[chave];
      renderFiltrosAtivos();
      carregar();
    });
  }

  function ligarFiltro(el, chave) {
    el.addEventListener("change", () => {
      filtros[chave] = el.value.trim ? el.value.trim() : el.value;
      renderFiltrosAtivos();
      carregar();
    });
  }

  filtroBusca.addEventListener("input", HRG.debounce(() => {
    filtros.q = filtroBusca.value.trim();
    renderFiltrosAtivos();
    carregar();
  }, 350));
  ligarFiltro(filtroServico, "servico");
  ligarFiltro(filtroStatus, "status");
  ligarFiltro(filtroAndar, "andar");
  ligarFiltro(filtroDataInicio, "data_inicio");
  ligarFiltro(filtroDataFim, "data_fim");

  const seletor = D.ligarSeletorPeriodo(document.getElementById("seletorPeriodo"), (valor) => {
    if (valor) filtros.periodo = valor; else delete filtros.periodo;
    carregar();
  });

  document.getElementById("botaoLimparFiltrosDash").addEventListener("click", () => {
    TODOS_OS_CAMPOS.forEach((el) => { el.value = ""; });
    Object.keys(filtros).forEach((chave) => delete filtros[chave]);
    seletor.marcar("");
    renderFiltrosAtivos();
    carregar();
  });

  HRG.pollWhileVisible(carregar, 30000);
})();
