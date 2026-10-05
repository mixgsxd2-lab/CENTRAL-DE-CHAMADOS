(function () {
  "use strict";

  const escapeHtml = HRG.escapeHtml;
  const formatarMinutos = HRG.formatarMinutos;

  // Meta de espera (30 min, ver hotelaria/models.py::META_ESPERA_MIN) —
  // mesmo selo de tempo da Central de Enfermagem: normal, alerta a partir de
  // 70% da meta e "atrasado" quando passa da meta.
  const LIMIAR_ALERTA_SLA = 0.7;

  function nivelTempoEspera(c) {
    if (c.acima_do_tempo_esperado) return "atrasado";
    if (c.status === "pendente" && c.sla_min && c.tempo_espera_min >= c.sla_min * LIMIAR_ALERTA_SLA) return "alerta";
    return "ok";
  }

  function seloTempoEspera(c) {
    const meta = c.sla_min != null ? ` <span class="meta-tempo">/ meta ${Math.round(c.sla_min)}min</span>` : "";
    return `<span class="selo-tempo selo-tempo-${nivelTempoEspera(c)}">⏱ ${formatarMinutos(c.tempo_espera_min)}${meta}</span>`;
  }

  // Central de Hotelaria mostra apenas chamados que ainda precisam de ação
  // (pendentes e em andamento). Finalizados vivem só na tela de Histórico.
  // Lista única (mesma estrutura/cartão da Central de Enfermagem) — pendentes
  // sempre à frente de em andamento, mas sem dividir em colunas separadas.
  const lista = document.getElementById("listaChamados");
  const filtroBusca = document.getElementById("filtroBusca");
  const filtroServico = document.getElementById("filtroServico");
  const filtroAndar = document.getElementById("filtroAndar");
  const filtrosAtivosEl = document.getElementById("filtrosAtivos");
  const botaoFiltrosAvancados = document.getElementById("botaoFiltrosAvancados");
  const painelFiltrosAvancados = document.getElementById("painelFiltrosAvancados");
  const fundoModal = document.getElementById("fundoModal");
  const modalChamado = document.getElementById("modalChamado");

  const filtros = {};
  let chamadoAbertoId = null;
  let controladorPollingModal = null;
  let ultimoSnapshotModal = null;
  const detectorLista = HRG.criarDetectorDeMudanca();
  // Detecta chegada de chamados novos (toca o alerta sonoro) — nunca de
  // novo para o mesmo chamado, mesmo que ele continue aparecendo em polls
  // seguintes (ver static/js/common.js).
  const detectorNovosChamados = HRG.criarDetectorDeNovosChamados();

  const ICONE_FECHAR = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>';

  async function carregarStats() {
    try {
      const { dados } = await HRG.fetchJSON("/hotelaria/api/central/resumo");
      document.getElementById("statPendentes").textContent = dados.pendentes;
      document.getElementById("statAndamento").textContent = dados.andamento;
      document.getElementById("statAtrasados").textContent = dados.acima_do_tempo;
      document.getElementById("statSetorTop").textContent = dados.setor_mais_requisitado_hoje || "—";
      document.getElementById("statFinalizadosHoje").textContent = dados.finalizados_hoje;
    } catch (e) {
      // Silencioso: o polling tenta de novo no próximo ciclo.
    }
  }

  async function carregarChamados() {
    const params = new URLSearchParams({ servico: filtroServico.value });
    // A Central pede só os ativos ao servidor (evita transportar finalizados
    // que nem seriam renderizados aqui, e mantém o polling leve).
    params.set("status_ativos", "1");
    if (filtroAndar.value) params.set("andar", filtroAndar.value);
    if (filtroBusca.value.trim()) params.set("q", filtroBusca.value.trim());

    let chamados;
    try {
      const { dados } = await HRG.fetchJSON(`/hotelaria/api/central/chamados?${params.toString()}`);
      chamados = dados;
    } catch (e) {
      return; // mantém a última visão conhecida na tela em caso de instabilidade de rede
    }

    const novos = detectorNovosChamados(chamados);
    if (novos.length) HRG.tocarAlertaNovoChamado();

    if (!detectorLista(chamados)) return;
    renderLista(chamados);
  }

  function renderLista(chamados) {
    // Finalizados são filtrados aqui também para blindar contra qualquer
    // reintrodução involuntária pelo endpoint (a Central deve mostrar
    // apenas chamados ativos; finalizados só no Histórico).
    const ativos = chamados.filter((c) => c.status !== "finalizado");
    if (!ativos.length) {
      lista.innerHTML = `<div class="estado-vazio">Nenhum chamado encontrado com estes filtros.</div>`;
      return;
    }
    // Pendentes sempre à frente de em andamento (quem ainda não foi assumido
    // aparece primeiro) e, dentro de cada grupo, quem espera há mais tempo
    // primeiro — mesmo critério da Central de Enfermagem.
    const porEspera = (a, b) => (b.tempo_espera_min || 0) - (a.tempo_espera_min || 0);
    const pendentes = ativos.filter((c) => c.status === "pendente").sort(porEspera);
    const andamento = ativos.filter((c) => c.status === "em_andamento").sort(porEspera);
    lista.innerHTML = pendentes.concat(andamento).map(cartaoChamadoHtml).join("");
    lista.querySelectorAll(".cartao-chamado-admin").forEach((elCard) => {
      elCard.addEventListener("click", () => abrirModal(parseInt(elCard.dataset.id, 10)));
    });
  }

  function cartaoChamadoHtml(c) {
    const borda = c.status === "pendente" ? "borda-alta" : "borda-andamento";
    return `
      <button type="button" class="cartao-chamado-admin ${borda} surgir" data-id="${c.id}">
        <div class="linha-cartao-admin">
          <span class="leito-etiqueta-admin">Leito ${escapeHtml(c.leito)}${c.andar ? ` · ${escapeHtml(c.andar)}` : ""}</span>
          <span class="servico-etiqueta">${escapeHtml(c.servico_nome)}</span>
        </div>
        <div class="categoria-cartao-admin">${escapeHtml(c.descricao_exibicao || c.descricao)}</div>
        <div class="rodape-cartao-admin">
          <span class="selo-status selo-status-${c.status}">${escapeHtml(rotuloStatus(c.status))}</span>
          ${seloTempoEspera(c)}
        </div>
      </button>
    `;
  }

  // ---------------------------------------------------------------------
  // Filtros ativos (busca/andar) — servico já tem seu próprio select visível.
  // ---------------------------------------------------------------------
  function renderFiltrosAtivos() {
    const ativos = [];
    if (filtroBusca.value.trim()) ativos.push({ chave: "busca", texto: `Busca: "${filtroBusca.value.trim()}"` });
    if (filtroAndar.value) ativos.push({ chave: "andar", texto: `Andar: ${filtroAndar.value}` });

    if (!ativos.length) { filtrosAtivosEl.innerHTML = ""; return; }
    filtrosAtivosEl.innerHTML = ativos.map((a) => `
      <span class="filtro-ativo-chip" data-chave="${a.chave}">${escapeHtml(a.texto)}<button type="button" aria-label="Remover filtro">✕</button></span>
    `).join("");
    filtrosAtivosEl.querySelectorAll(".filtro-ativo-chip button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const chave = botao.parentElement.dataset.chave;
        if (chave === "busca") filtroBusca.value = "";
        if (chave === "andar") filtroAndar.value = "";
        renderFiltrosAtivos();
        carregarChamados();
      });
    });
  }

  // ---------------------------------------------------------------------
  // Modal do chamado
  // ---------------------------------------------------------------------
  async function abrirModal(id) {
    chamadoAbertoId = id;
    fundoModal.classList.add("aberto");
    modalChamado.innerHTML = `<p style="text-align:center; padding:40px;">Carregando...</p>`;
    ultimoSnapshotModal = null;

    await renderModal();
    iniciarPollingModal();
  }

  async function renderModal() {
    if (!chamadoAbertoId) return;
    let c;
    try {
      const { dados } = await HRG.fetchJSON(`/hotelaria/api/chamados/${chamadoAbertoId}`);
      c = dados;
    } catch (e) {
      modalChamado.innerHTML = `<p style="text-align:center; padding:40px;">Não foi possível carregar este chamado.</p>`;
      return;
    }
    ultimoSnapshotModal = `${c.status}|${c.confirmacao_resolucao}|${c.tem_avaliacao}|${c.acima_do_tempo_esperado}`;

    const confirmacaoTexto = {
      pendente: "Aguardando confirmação do paciente",
      resolvido: "✅ Paciente confirmou: problema resolvido",
      nao_resolvido: "⚠️ Paciente informou: problema não resolvido",
      expirada: "⏱ Prazo de confirmação expirado sem resposta",
      nao_aplicavel: "—",
    }[c.confirmacao_resolucao] || "—";

    const acoes = [];
    if (c.status === "pendente") {
      acoes.push(`<button class="botao" id="botaoAssumir">Assumir chamado</button>`);
    }
    if (c.status === "em_andamento") {
      acoes.push(`<button class="botao sucesso" id="botaoFinalizar">Finalizar atendimento</button>`);
    }

    modalChamado.innerHTML = `
      <div class="modal-topo">
        <div>
          <h2 style="margin:0 0 4px;">Leito ${escapeHtml(c.leito)}</h2>
          <span class="servico-etiqueta">${escapeHtml(c.servico_nome)}</span>
          ${c.acima_do_tempo_esperado ? `<span class="selo-atrasado" style="margin-left:6px;">Acima do tempo esperado</span>` : ""}
        </div>
        <button class="fechar-modal" id="botaoFecharModal" aria-label="Fechar">${ICONE_FECHAR}</button>
      </div>

      <div class="bloco-info-modal">
        <div><b>Local:</b> ${c.andar ? escapeHtml(c.andar) + " · " : ""}Leito ${escapeHtml(c.leito)}</div>
        <div><b>Status:</b> ${rotuloStatus(c.status)}</div>
        <div><b>Descrição:</b> ${escapeHtml(c.descricao_exibicao || c.descricao)}</div>
        <div><b>Aberto em:</b> ${c.criado_em}</div>
        ${c.iniciado_em ? `<div><b>Assumido em:</b> ${c.iniciado_em}</div>` : ""}
        ${c.finalizado_em ? `<div><b>Finalizado em:</b> ${c.finalizado_em}</div>` : ""}
        <div><b>Tempo de espera:</b> ${seloTempoEspera(c)}</div>
        ${c.status === "finalizado" ? `<div><b>Confirmação:</b> ${confirmacaoTexto}</div>` : ""}
      </div>

      <div class="linha-acoes-modal">${acoes.join("")}</div>
    `;

    document.getElementById("botaoFecharModal").addEventListener("click", fecharModal);
    const btnAssumir = document.getElementById("botaoAssumir");
    if (btnAssumir) btnAssumir.addEventListener("click", () => HRG.comBotaoTravado(btnAssumir, () => alterarStatus(c.id, "em_andamento", true)));
    const btnFinalizar = document.getElementById("botaoFinalizar");
    if (btnFinalizar) btnFinalizar.addEventListener("click", () => HRG.comBotaoTravado(btnFinalizar, () => alterarStatus(c.id, "finalizado")));
  }

  function rotuloStatus(status) {
    return { pendente: "Pendente", em_andamento: "Em andamento", finalizado: "Finalizado" }[status] || status;
  }

  function fecharModal() {
    fundoModal.classList.remove("aberto");
    chamadoAbertoId = null;
    pararPollingModal();
  }

  async function alterarStatus(id, novoStatus, assumir) {
    const endpoint = assumir ? `/hotelaria/api/central/chamados/${id}/assumir` : `/hotelaria/api/central/chamados/${id}/status`;
    const opcoes = { method: "POST", headers: { "Content-Type": "application/json" } };
    if (!assumir) opcoes.body = JSON.stringify({ status: novoStatus });
    try {
      await HRG.fetchJSON(endpoint, opcoes);
      if (novoStatus === "finalizado") {
        // Finalizado = sai da Central (vai para o Histórico): fecha o
        // detalhe automaticamente.
        fecharModal();
        HRG.toast("Chamado finalizado.", "sucesso");
      } else {
        await renderModal();
      }
      await Promise.all([carregarStats(), carregarChamados()]);
    } catch (err) {
      HRG.toast(err.message, "erro");
    }
  }

  // ---------------------------------------------------------------------
  // Polling do modal aberto: se o status/confirmação/avaliação mudou (ex.:
  // o paciente avaliou, ou a confirmação expirou), o modal é atualizado.
  // ---------------------------------------------------------------------
  function iniciarPollingModal() {
    pararPollingModal();
    controladorPollingModal = HRG.pollWhileVisible(async () => {
      if (!chamadoAbertoId) return;
      let c;
      try {
        const { dados } = await HRG.fetchJSON(`/hotelaria/api/chamados/${chamadoAbertoId}`);
        c = dados;
      } catch (e) {
        return;
      }
      if (c.status === "finalizado") {
        // Finalizado por outra pessoa enquanto o detalhe estava aberto.
        fecharModal();
        return;
      }
      const snapshot = `${c.status}|${c.confirmacao_resolucao}|${c.tem_avaliacao}|${c.acima_do_tempo_esperado}`;
      if (snapshot !== ultimoSnapshotModal) {
        await renderModal();
      }
    }, 4000);
  }

  function pararPollingModal() {
    if (controladorPollingModal) { controladorPollingModal.parar(); controladorPollingModal = null; }
  }

  async function carregarTudo() {
    await Promise.all([carregarStats(), carregarChamados()]);
  }

  filtroServico.addEventListener("change", carregarChamados);
  filtroAndar.addEventListener("change", () => { renderFiltrosAtivos(); carregarChamados(); });
  filtroBusca.addEventListener("input", HRG.debounce(() => { renderFiltrosAtivos(); carregarChamados(); }, 350));

  botaoFiltrosAvancados.addEventListener("click", () => {
    const abrir = painelFiltrosAvancados.hidden;
    painelFiltrosAvancados.hidden = !abrir;
    botaoFiltrosAvancados.setAttribute("aria-expanded", String(abrir));
  });
  fundoModal.addEventListener("click", (e) => { if (e.target === fundoModal) fecharModal(); });
  HRG.fecharComEsc(() => fundoModal.classList.contains("aberto"), fecharModal);

  HRG.pollWhileVisible(carregarTudo, 5000);
})();
