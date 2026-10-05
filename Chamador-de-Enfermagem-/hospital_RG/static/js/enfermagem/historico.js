(function () {
  "use strict";

  const escapeHtml = HRG.escapeHtml;
  const formatarMinutos = HRG.formatarMinutos;

  const lista = document.getElementById("listaHistorico");
  const fundoModal = document.getElementById("fundoModal");
  const modalChamado = document.getElementById("modalChamado");
  const filtrosAtivosEl = document.getElementById("filtrosAtivos");
  const paginacaoEl = document.getElementById("paginacaoHistorico");
  const textoPaginacao = document.getElementById("textoPaginacao");
  const botaoCarregarMais = document.getElementById("botaoCarregarMais");

  const filtroBusca = document.getElementById("filtroBusca");
  const filtroPrioridade = document.getElementById("filtroPrioridade");
  const filtroAndar = document.getElementById("filtroAndar");
  const filtroLeito = document.getElementById("filtroLeito");
  const filtroCategoria = document.getElementById("filtroCategoria");
  const filtroPeriodo = document.getElementById("filtroPeriodo");
  const filtroOrdenar = document.getElementById("filtroOrdenar");
  const botaoLimparFiltrosHistorico = document.getElementById("botaoLimparFiltrosHistorico");
  const botaoFiltrosAvancados = document.getElementById("botaoFiltrosAvancados");
  const painelFiltrosAvancados = document.getElementById("painelFiltrosAvancados");

  if (botaoFiltrosAvancados && painelFiltrosAvancados) {
    botaoFiltrosAvancados.addEventListener("click", () => {
      const abrir = painelFiltrosAvancados.hidden;
      painelFiltrosAvancados.hidden = !abrir;
      botaoFiltrosAvancados.setAttribute("aria-expanded", String(abrir));
    });
  }

  const TAMANHO_PAGINA = 30;
  let acumulado = [];
  let totalConhecido = 0;

  function filtrosAtuais() {
    const params = new URLSearchParams({ status: "finalizado" });
    if (filtroBusca.value.trim()) params.set("q", filtroBusca.value.trim());
    if (filtroPrioridade.value) params.set("prioridade", filtroPrioridade.value);
    if (filtroAndar.value) params.set("andar", filtroAndar.value);
    if (filtroLeito.value.trim()) params.set("leito", filtroLeito.value.trim());
    if (filtroCategoria.value) params.set("categoria", filtroCategoria.value);
    if (filtroPeriodo.value) params.set("periodo", filtroPeriodo.value);
    if (filtroOrdenar.value) params.set("ordenar", filtroOrdenar.value);
    return params;
  }

  async function carregarMetricas() {
    try {
      const { dados: m } = await HRG.fetchJSON(`/api/enfermagem/metricas?${filtrosAtuais().toString()}`);
      document.getElementById("mTotal").textContent = m.total;
      document.getElementById("mTempoEspera").textContent = m.tempo_medio_espera_min != null ? formatarMinutos(m.tempo_medio_espera_min) : "—";
      document.getElementById("mTempoAtendimento").textContent = m.tempo_medio_atendimento_min != null ? formatarMinutos(m.tempo_medio_atendimento_min) : "—";
      document.getElementById("mAvaliacao").textContent = m.total_avaliacoes ? `${m.avaliacao_media} ★` : "—";
    } catch (e) {
      // Os cartões simplesmente mantêm o último valor conhecido.
    }
  }

  async function carregarLista(reiniciar) {
    if (reiniciar) { acumulado = []; }
    const params = filtrosAtuais();
    params.set("limite", TAMANHO_PAGINA);
    params.set("offset", acumulado.length);

    try {
      const { dados, resposta } = await HRG.fetchJSON(`/api/enfermagem/chamados?${params.toString()}`);
      acumulado = acumulado.concat(dados);
      totalConhecido = parseInt(resposta.headers.get("X-Total-Count") || acumulado.length, 10);
      renderLista(acumulado);
      atualizarPaginacao();
    } catch (e) {
      if (!acumulado.length) {
        lista.innerHTML = `<div class="estado-vazio">Não foi possível carregar o histórico. Verifique sua conexão.</div>`;
      }
    }
  }

  function atualizarPaginacao() {
    if (!acumulado.length) { paginacaoEl.hidden = true; return; }
    paginacaoEl.hidden = false;
    textoPaginacao.textContent = `Mostrando ${acumulado.length} de ${totalConhecido}`;
    botaoCarregarMais.hidden = acumulado.length >= totalConhecido;
  }

  function renderLista(chamados) {
    if (!chamados.length) {
      lista.innerHTML = `
        <div class="estado-vazio">
          <span>Nenhum chamado encontrado com estes filtros.</span>
          <button class="botao botao-fantasma pequeno" id="botaoLimparNoVazio" type="button">Limpar filtros</button>
        </div>`;
      const botao = document.getElementById("botaoLimparNoVazio");
      if (botao) botao.addEventListener("click", limparFiltros);
      return;
    }
    lista.innerHTML = chamados.map(cartaoHtml).join("");
    lista.querySelectorAll(".cartao-chamado-admin").forEach((elCard) => {
      elCard.addEventListener("click", () => abrirModal(parseInt(elCard.dataset.id, 10)));
    });
  }

  function cartaoHtml(c) {
    return `
      <button type="button" class="cartao-chamado-admin borda-${c.prioridade} surgir" data-id="${c.id}">
        <div class="linha-cartao-admin">
          <span class="leito-etiqueta-admin">Leito ${escapeHtml(c.leito)}</span>
          <span class="selo-prioridade selo-${c.prioridade}">${c.prioridade_emoji} ${c.prioridade_label}</span>
        </div>
        <div class="categoria-cartao-admin">${escapeHtml(c.categoria)} — ${escapeHtml(c.subcategoria)}</div>
        <div class="rodape-cartao-admin">
          <span class="selo-status selo-status-${c.status}">${escapeHtml(c.status_label)}</span>
          <span>${c.criado_em}</span>
          ${c.tempo_atendimento_min != null ? `<span>${formatarMinutos(c.tempo_atendimento_min)} de atendimento</span>` : ""}
        </div>
      </button>
    `;
  }

  function abrirModal(id) {
    const c = acumulado.find((x) => x.id === id);
    if (!c) return;
    fundoModal.classList.add("aberto");
    modalChamado.innerHTML = `
      <div class="modal-topo-admin">
        <div>
          <h2>Leito ${escapeHtml(c.leito)}</h2>
          <span class="selo-prioridade selo-${c.prioridade}">${c.prioridade_emoji} ${c.prioridade_label}</span>
        </div>
        <button class="fechar-modal" id="botaoFecharModal" aria-label="Fechar">✕</button>
      </div>
      <span class="etiqueta-somente-leitura">🔒 Histórico — somente leitura</span>
      <div class="bloco-info-admin">
        <div><b>Identificação:</b> #${c.id}</div>
        <div><b>Solicitação:</b> ${escapeHtml(c.categoria)} — ${escapeHtml(c.subcategoria)}</div>
        ${c.detalhe ? `<div><b>Detalhe:</b> ${escapeHtml(c.detalhe)}</div>` : ""}
        <div><b>Status:</b> ${escapeHtml(c.status_label)}</div>
        <div><b>Aberto em:</b> ${c.criado_em}</div>
        ${c.inicio_atendimento ? `<div><b>Assumido em:</b> ${c.inicio_atendimento}</div>` : "<div>—</div>"}
        ${c.finalizado_em ? `<div><b>Finalizado em:</b> ${c.finalizado_em}</div>` : ""}
        <div><b>Tempo de espera:</b> ${formatarMinutos(c.tempo_espera_min)}</div>
        ${c.tempo_atendimento_min != null ? `<div><b>Tempo de atendimento:</b> ${formatarMinutos(c.tempo_atendimento_min)}</div>` : ""}
        <div><b>Avaliação do paciente:</b> ${c.avaliacao != null ? `${"★".repeat(c.avaliacao)}${"☆".repeat(5 - c.avaliacao)}` : "Não avaliado"}</div>
        ${c.comentario_avaliacao ? `<div><b>Comentário:</b> "${escapeHtml(c.comentario_avaliacao)}"</div>` : ""}
      </div>
    `;
    document.getElementById("botaoFecharModal").addEventListener("click", fecharModal);
  }

  function fecharModal() {
    fundoModal.classList.remove("aberto");
  }

  fundoModal.addEventListener("click", (e) => { if (e.target === fundoModal) fecharModal(); });
  HRG.fecharComEsc(() => fundoModal.classList.contains("aberto"), fecharModal);

  function recarregarTudo() {
    carregarMetricas();
    carregarLista(true);
  }

  // ---------------------------------------------------------------------
  // Filtros ativos
  // ---------------------------------------------------------------------
  function limparFiltros() {
    filtroBusca.value = ""; filtroPrioridade.value = "";
    filtroAndar.value = ""; filtroLeito.value = ""; filtroCategoria.value = "";
    filtroPeriodo.value = ""; filtroOrdenar.value = "recentes";
    renderFiltrosAtivos();
    recarregarTudo();
  }

  function renderFiltrosAtivos() {
    const definicoes = [
      { chave: "q", el: filtroBusca, rotulo: (v) => `Busca: "${v}"` },
      { chave: "prioridade", el: filtroPrioridade, rotulo: (v) => `Prioridade: ${filtroPrioridade.selectedOptions[0].textContent}` },
      { chave: "andar", el: filtroAndar, rotulo: () => `Andar: ${filtroAndar.selectedOptions[0].textContent}` },
      { chave: "leito", el: filtroLeito, rotulo: (v) => `Leito: ${v}` },
      { chave: "categoria", el: filtroCategoria, rotulo: (v) => `Tipo: ${v}` },
      { chave: "periodo", el: filtroPeriodo, rotulo: (v) => filtroPeriodo.selectedOptions[0].textContent },
    ];
    const ativos = definicoes.filter((d) => d.el.value);
    if (!ativos.length) { filtrosAtivosEl.innerHTML = ""; return; }
    filtrosAtivosEl.innerHTML = ativos.map((d) => `
      <span class="filtro-ativo-chip" data-chave="${d.chave}">${escapeHtml(d.rotulo(d.el.value))}<button type="button" aria-label="Remover filtro">✕</button></span>
    `).join("");
    filtrosAtivosEl.querySelectorAll(".filtro-ativo-chip button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const chave = botao.parentElement.dataset.chave;
        const def = definicoes.find((d) => d.chave === chave);
        if (def) def.el.value = "";
        renderFiltrosAtivos();
        recarregarTudo();
      });
    });
  }

  [filtroPrioridade, filtroAndar, filtroCategoria, filtroPeriodo, filtroOrdenar].forEach((sel) => {
    sel.addEventListener("change", () => { renderFiltrosAtivos(); recarregarTudo(); });
  });
  filtroLeito.addEventListener("input", HRG.debounce(() => { renderFiltrosAtivos(); recarregarTudo(); }, 350));
  filtroBusca.addEventListener("input", HRG.debounce(() => { renderFiltrosAtivos(); recarregarTudo(); }, 350));
  botaoLimparFiltrosHistorico.addEventListener("click", limparFiltros);
  botaoCarregarMais.addEventListener("click", () => carregarLista(false));

  filtroOrdenar.value = "recentes";
  recarregarTudo();
})();
