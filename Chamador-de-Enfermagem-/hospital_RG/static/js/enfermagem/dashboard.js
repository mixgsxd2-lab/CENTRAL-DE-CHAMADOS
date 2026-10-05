(function () {
  "use strict";

  // Gráficos, cartões, seletor de período e chips de filtro vêm de
  // static/js/dashboard_comum.js — o mesmo sistema usado pelo Dashboard da
  // Hotelaria (static/js/hotelaria/dashboard.js).
  const D = HRGDashboard;
  const P = D.PALETA;
  const formatarMinutos = HRG.formatarMinutos;

  // Prioridade na escala de azuis da paleta: quanto mais grave, mais escuro.
  const FAIXAS_PRIORIDADE = [
    { chave: "critica", rotulo: "Crítico", cor: P[0], rodape: ["crítico", "críticos"] },
    { chave: "media", rotulo: "Médio" },
    { chave: "baixa", rotulo: "Baixo" },
  ];

  const filtros = {};
  const filtroBusca = document.getElementById("filtroBusca");
  const filtroStatus = document.getElementById("filtroStatus");
  const filtroPrioridade = document.getElementById("filtroPrioridade");
  const filtroAndar = document.getElementById("filtroAndar");
  const filtroCategoria = document.getElementById("filtroCategoria");
  const filtroDataInicio = document.getElementById("filtroDataInicio");
  const filtroDataFim = document.getElementById("filtroDataFim");
  const filtrosAtivosEl = document.getElementById("filtrosAtivos");

  D.ligarPainelFiltros(document.getElementById("botaoFiltrosAvancados"), document.getElementById("painelFiltrosAvancados"));
  document.getElementById("legendaAndar").innerHTML = D.legendaHtml(FAIXAS_PRIORIDADE);

  const TODOS_OS_CAMPOS = [filtroBusca, filtroStatus, filtroPrioridade, filtroAndar, filtroCategoria, filtroDataInicio, filtroDataFim];

  async function carregar() {
    const params = new URLSearchParams();
    Object.entries(filtros).forEach(([chave, valor]) => { if (valor) params.set(chave, valor); });

    try {
      const { dados } = await HRG.fetchJSON(`/api/enfermagem/metricas?${params.toString()}`);
      renderCartoes(dados);
      D.renderBarras(document.getElementById("graficoCategoria"),
        Object.entries(dados.por_categoria || {}).map(([rotulo, valor]) => ({ rotulo, valor })));
      D.renderBarras(document.getElementById("graficoPrioridade"),
        FAIXAS_PRIORIDADE.map((fx) => ({ rotulo: fx.rotulo, valor: (dados.por_prioridade || {})[fx.chave] || 0, cor: fx.cor })));
      D.renderPeriodo(document.getElementById("graficoPeriodo"), document.getElementById("subtituloPeriodo"), dados.serie_periodo);
      D.renderEmpilhado(document.getElementById("graficoAndar"), dados.por_andar_prioridade, FAIXAS_PRIORIDADE, "critica");
    } catch (e) {
      HRG.toast("Não foi possível atualizar o dashboard.", "erro");
    }
  }

  function renderCartoes(d) {
    D.renderCartoes(document.getElementById("cartoesResumo"), [
      { rotulo: "Total de chamados", valor: d.total, destaque: true, extra: D.tendenciaHtml(d.comparativo_periodo_anterior) },
      { rotulo: "Pendentes", valor: d.pendentes },
      { rotulo: "Em atendimento", valor: d.em_atendimento },
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
      { chave: "status", el: filtroStatus, rotulo: () => `Status: ${filtroStatus.selectedOptions[0].textContent}` },
      { chave: "prioridade", el: filtroPrioridade, rotulo: () => `Prioridade: ${filtroPrioridade.selectedOptions[0].textContent}` },
      { chave: "andar", el: filtroAndar, rotulo: () => `Andar: ${filtroAndar.selectedOptions[0].textContent}` },
      { chave: "categoria", el: filtroCategoria, rotulo: (v) => `Tipo: ${v}` },
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
  ligarFiltro(filtroStatus, "status");
  ligarFiltro(filtroPrioridade, "prioridade");
  ligarFiltro(filtroAndar, "andar");
  ligarFiltro(filtroCategoria, "categoria");
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

  // `pollWhileVisible` já faz a primeira chamada imediatamente, então não é
  // preciso chamar `carregar()` de novo aqui antes de agendar o polling.
  HRG.pollWhileVisible(carregar, 30000);
})();
