(function () {
  "use strict";

  const escapeHtml = HRG.escapeHtml;

  const filtroBusca = document.getElementById("filtroBusca");
  const filtroServico = document.getElementById("filtroServicoHistorico");
  const filtroAndar = document.getElementById("filtroAndar");
  const filtroLeito = document.getElementById("filtroLeito");
  const filtroPeriodo = document.getElementById("filtroPeriodo");
  const filtroOrdenar = document.getElementById("filtroOrdenar");
  const botaoLimparFiltrosHistorico = document.getElementById("botaoLimparFiltrosHistorico");
  const lista = document.getElementById("listaHistorico");
  const fundoModal = document.getElementById("fundoModal");
  const modalChamado = document.getElementById("modalChamado");
  const filtrosAtivosEl = document.getElementById("filtrosAtivos");
  const paginacaoEl = document.getElementById("paginacaoHistorico");
  const textoPaginacao = document.getElementById("textoPaginacao");
  const botaoCarregarMais = document.getElementById("botaoCarregarMais");
  const botaoFiltrosAvancados = document.getElementById("botaoFiltrosAvancados");
  const painelFiltrosAvancados = document.getElementById("painelFiltrosAvancados");

  if (botaoFiltrosAvancados && painelFiltrosAvancados) {
    botaoFiltrosAvancados.addEventListener("click", () => {
      const abrir = painelFiltrosAvancados.hidden;
      painelFiltrosAvancados.hidden = !abrir;
      botaoFiltrosAvancados.setAttribute("aria-expanded", String(abrir));
    });
  }

  const ICONE_FECHAR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  const TAMANHO_PAGINA = 30;
  let acumulado = [];
  let totalConhecido = 0;

  function filtrosAtuais() {
    const params = new URLSearchParams({ servico: filtroServico.value, status: "finalizado" });
    if (filtroAndar.value) params.set("andar", filtroAndar.value);
    if (filtroLeito.value.trim()) params.set("leito", filtroLeito.value.trim());
    if (filtroBusca.value.trim()) params.set("q", filtroBusca.value.trim());
    if (filtroPeriodo.value) params.set("periodo", filtroPeriodo.value);
    if (filtroOrdenar.value) params.set("ordenar", filtroOrdenar.value);
    return params;
  }

  async function carregarMetricas() {
    try {
      const { dados: m } = await HRG.fetchJSON(`/hotelaria/api/dashboard/resumo?${filtrosAtuais().toString()}`);
      document.getElementById("mTotal").textContent = m.total;
      document.getElementById("mTempoEspera").textContent = m.tempo_medio_espera_min != null ? HRG.formatarMinutos(m.tempo_medio_espera_min) : "—";
      document.getElementById("mTempoAtendimento").textContent = m.tempo_medio_atendimento_min != null ? HRG.formatarMinutos(m.tempo_medio_atendimento_min) : "—";
      document.getElementById("mAvaliacao").textContent = m.total_avaliacoes ? `${m.media_avaliacao} ★` : "—";
    } catch (e) {
      // Os cartões simplesmente mantêm o último valor conhecido.
    }
  }

  async function carregarHistorico(reiniciar) {
    if (reiniciar) acumulado = [];
    const params = filtrosAtuais();
    params.set("limite", TAMANHO_PAGINA);
    params.set("offset", acumulado.length);

    try {
      const { dados, resposta } = await HRG.fetchJSON(`/hotelaria/api/central/chamados?${params.toString()}`);
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
    lista.innerHTML = chamados.map(cartaoHistoricoHtml).join("");
    lista.querySelectorAll(".cartao-chamado-admin").forEach((elCard) => {
      elCard.addEventListener("click", () => abrirModal(parseInt(elCard.dataset.id, 10)));
    });
  }

  // Mesma estrutura/classes do cartão de Histórico da Enfermagem (ver
  // enfermagem/historico.js::cartaoHtml) — Hotelaria não tem faixa de
  // prioridade, então o selo de serviço ocupa o lugar do selo de
  // prioridade, e a borda usa sempre o acento "baixa" (verde), já que aqui
  // só existem chamados finalizados.
  function cartaoHistoricoHtml(c) {
    return `
      <button type="button" class="cartao-chamado-admin borda-baixa surgir" data-id="${c.id}">
        <div class="linha-cartao-admin">
          <span class="leito-etiqueta-admin">Leito ${escapeHtml(c.leito)}</span>
          <span class="servico-etiqueta">${escapeHtml(c.servico_nome)}</span>
        </div>
        <div class="categoria-cartao-admin">${escapeHtml(c.descricao_exibicao || c.descricao)}</div>
        <div class="rodape-cartao-admin">
          <span class="selo-status selo-status-finalizado">Finalizado</span>
          <span>${c.criado_em}</span>
          ${c.tempo_atendimento_min != null ? `<span>${HRG.formatarMinutos(c.tempo_atendimento_min)} de atendimento</span>` : ""}
        </div>
      </button>
    `;
  }

  async function abrirModal(id) {
    fundoModal.classList.add("aberto");
    modalChamado.innerHTML = `<p style="text-align:center; padding:40px;">Carregando...</p>`;

    let c;
    try {
      const { dados } = await HRG.fetchJSON(`/hotelaria/api/chamados/${id}`);
      c = dados;
    } catch (e) {
      modalChamado.innerHTML = `<p style="text-align:center; padding:40px;">Não foi possível carregar este chamado.</p>`;
      return;
    }

    const confirmacaoTexto = {
      pendente: "Aguardando confirmação do paciente",
      resolvido: "✅ Paciente confirmou: problema resolvido",
      nao_resolvido: "⚠️ Paciente informou: problema não resolvido",
      expirada: "⏱ Prazo de confirmação expirado sem resposta",
      nao_aplicavel: "—",
    }[c.confirmacao_resolucao] || "—";

    const avaliacaoHtml = c.avaliacao
      ? `<div class="avaliacao-exibicao">${"★".repeat(c.avaliacao.estrelas)}${"☆".repeat(5 - c.avaliacao.estrelas)} <span style="color:var(--texto-suave); font-weight:500;">(${c.avaliacao.estrelas}/5)</span></div>
         ${c.avaliacao.comentario ? `<p style="font-size:0.85rem; color:var(--texto-suave); margin-top:6px;">Comentário: "${escapeHtml(c.avaliacao.comentario)}"</p>` : `<p style="font-size:0.82rem; color:var(--texto-suave); margin-top:6px;">Sem comentário.</p>`}`
      : `<span style="color:var(--texto-suave); font-size:0.85rem;">Não avaliado pelo paciente</span>`;

    modalChamado.innerHTML = `
      <div class="modal-topo">
        <div>
          <h2 style="margin:0 0 4px;">Leito ${escapeHtml(c.leito)}</h2>
          <span class="servico-etiqueta">${escapeHtml(c.servico_nome)}</span>
        </div>
        <button class="fechar-modal" id="botaoFecharModalHistorico" aria-label="Fechar">${ICONE_FECHAR}</button>
      </div>

      <span class="etiqueta-somente-leitura">🔒 Chamado finalizado · somente leitura</span>

      <div class="bloco-info-modal">
        <div><b>Identificação:</b> #${c.id}</div>
        <div><b>Local:</b> ${c.andar ? escapeHtml(c.andar) + " · " : ""}Leito ${escapeHtml(c.leito)}</div>
        <div><b>Descrição:</b> ${escapeHtml(c.descricao_exibicao || c.descricao)}</div>
        <div><b>Aberto em:</b> ${c.criado_em || "—"}</div>
        <div><b>Finalizado em:</b> ${c.finalizado_em || "—"}</div>
        <div><b>Tempo total de atendimento:</b> ${c.tempo_atendimento_min != null ? `${c.tempo_atendimento_min} min` : "—"}</div>
        <div><b>Confirmação do paciente:</b> ${confirmacaoTexto}</div>
      </div>

      <div class="bloco-info-modal" style="margin-top:14px;">
        <b>Avaliação do paciente</b><br>
        ${avaliacaoHtml}
      </div>
    `;

    document.getElementById("botaoFecharModalHistorico").addEventListener("click", fecharModal);
  }

  function fecharModal() {
    fundoModal.classList.remove("aberto");
  }

  fundoModal.addEventListener("click", (e) => { if (e.target === fundoModal) fecharModal(); });
  HRG.fecharComEsc(() => fundoModal.classList.contains("aberto"), fecharModal);

  function recarregarTudo() {
    carregarMetricas();
    carregarHistorico(true);
  }

  // ---------------------------------------------------------------------
  // Filtros ativos
  // ---------------------------------------------------------------------
  function limparFiltros() {
    filtroBusca.value = ""; filtroServico.value = "todos"; filtroAndar.value = "";
    filtroLeito.value = ""; filtroPeriodo.value = ""; filtroOrdenar.value = "recentes";
    renderFiltrosAtivos();
    recarregarTudo();
  }

  function renderFiltrosAtivos() {
    const definicoes = [
      { chave: "q", el: filtroBusca, rotulo: (v) => `Busca: "${v}"` },
      { chave: "servico", el: filtroServico, ignorar: "todos", rotulo: () => `Serviço: ${filtroServico.selectedOptions[0].textContent}` },
      { chave: "andar", el: filtroAndar, rotulo: (v) => `Andar: ${v}` },
      { chave: "leito", el: filtroLeito, rotulo: (v) => `Leito: ${v}` },
      { chave: "periodo", el: filtroPeriodo, rotulo: () => filtroPeriodo.selectedOptions[0].textContent },
    ];
    const ativos = definicoes.filter((d) => d.el.value && d.el.value !== d.ignorar);
    if (!ativos.length) { filtrosAtivosEl.innerHTML = ""; return; }
    filtrosAtivosEl.innerHTML = ativos.map((d) => `
      <span class="filtro-ativo-chip" data-chave="${d.chave}">${escapeHtml(d.rotulo(d.el.value))}<button type="button" aria-label="Remover filtro">✕</button></span>
    `).join("");
    filtrosAtivosEl.querySelectorAll(".filtro-ativo-chip button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const chave = botao.parentElement.dataset.chave;
        const def = definicoes.find((d) => d.chave === chave);
        if (def) def.el.value = def.ignorar || "";
        renderFiltrosAtivos();
        recarregarTudo();
      });
    });
  }

  [filtroServico, filtroAndar, filtroPeriodo, filtroOrdenar].forEach((sel) => {
    sel.addEventListener("change", () => { renderFiltrosAtivos(); recarregarTudo(); });
  });
  filtroLeito.addEventListener("input", HRG.debounce(() => { renderFiltrosAtivos(); recarregarTudo(); }, 350));
  filtroBusca.addEventListener("input", HRG.debounce(() => { renderFiltrosAtivos(); recarregarTudo(); }, 350));
  botaoLimparFiltrosHistorico.addEventListener("click", limparFiltros);
  botaoCarregarMais.addEventListener("click", () => carregarHistorico(false));

  filtroOrdenar.value = "recentes";
  recarregarTudo();
})();
