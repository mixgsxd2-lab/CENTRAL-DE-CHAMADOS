(function () {
  "use strict";

  const escapeHtml = HRG.escapeHtml;
  const formatarMinutos = HRG.formatarMinutos;

  // A partir de quanto da meta do SLA já consumida o selo de tempo de
  // espera passa de "ok" para "alerta" (antes de efetivamente estourar e
  // virar "atrasado", que é quem manda no `acima_do_tempo_esperado` vindo
  // do backend — ver enfermagem/priority.py::excedeu_sla).
  const LIMIAR_ALERTA_SLA = 0.7;

  function nivelTempoEspera(c) {
    if (c.acima_do_tempo_esperado) return "atrasado";
    if (c.sla_min && c.tempo_espera_min >= c.sla_min * LIMIAR_ALERTA_SLA) return "alerta";
    return "ok";
  }

  function seloTempoEspera(c) {
    const meta = c.sla_min != null ? ` <span class="meta-tempo">/ meta ${Math.round(c.sla_min)}min</span>` : "";
    return `<span class="selo-tempo selo-tempo-${nivelTempoEspera(c)}">⏱ ${formatarMinutos(c.tempo_espera_min)}${meta}</span>`;
  }

  const lista = document.getElementById("listaChamados");
  const fundoModal = document.getElementById("fundoModal");
  const modalChamado = document.getElementById("modalChamado");
  const filtrosAtivosEl = document.getElementById("filtrosAtivos");

  const chipsStatus = document.getElementById("chipsStatus");
  const chipsPrioridade = document.getElementById("chipsPrioridade");
  const botaoFiltrosAvancados = document.getElementById("botaoFiltrosAvancados");
  const painelFiltrosAvancados = document.getElementById("painelFiltrosAvancados");
  const filtroBusca = document.getElementById("filtroBusca");
  const filtroAndar = document.getElementById("filtroAndar");
  const filtroLeito = document.getElementById("filtroLeito");
  const filtroCategoria = document.getElementById("filtroCategoria");
  const filtroPeriodo = document.getElementById("filtroPeriodo");
  const filtroOrdenar = document.getElementById("filtroOrdenar");
  const botaoLimparFiltros = document.getElementById("botaoLimparFiltros");

  // A Central mostra apenas chamados que ainda precisam de ação — finalizados
  // vivem só no Histórico. O filtro de status "" (Todos ativos) e as opções
  // "Pendentes" / "Em atendimento" são as únicas expostas na UI, e no
  // servidor pedimos a lista já sem finalizados (`status_ativos=1`).
  const filtros = { status: "", prioridade: "", status_ativos: "1" };
  let chamadoAbertoId = null;
  let ultimaListaConhecida = [];
  const detectorLista = HRG.criarDetectorDeMudanca();
  // Detecta chegada de chamados novos a partir da fila completa (sem
  // filtro) do /tv — assim, trocar os filtros da lista abaixo nunca soa o
  // alerta por engano para um chamado que só "reapareceu" na tela.
  const detectorNovosChamados = HRG.criarDetectorDeNovosChamados();

  // ---------------------------------------------------------------------
  // Carregamento
  // ---------------------------------------------------------------------
  async function carregarStats() {
    try {
      const { dados } = await HRG.fetchJSON("/api/enfermagem/tv");
      document.getElementById("statPendentes").textContent = dados.contadores.pendentes;
      document.getElementById("statEmAtendimento").textContent = dados.contadores.em_atendimento;
      document.getElementById("statCriticos").textContent = dados.contadores.criticos;
      document.getElementById("statAtrasados").textContent = dados.contadores.atrasados;
      document.getElementById("statFinalizadosHoje").textContent = dados.contadores.finalizados_hoje;

      const novos = detectorNovosChamados(dados.fila || []);
      if (novos.length) HRG.tocarAlertaNovoChamado();
    } catch (e) {
      // Silencioso: o polling tenta de novo no próximo ciclo. Um erro aqui
      // não deve interromper a lista principal, que tem seu próprio tratamento.
    }
  }

  function paramsAtuais() {
    const params = new URLSearchParams();
    Object.entries(filtros).forEach(([chave, valor]) => { if (valor) params.set(chave, valor); });
    return params;
  }

  async function carregarLista() {
    const params = paramsAtuais();
    let chamados;
    try {
      const { dados } = await HRG.fetchJSON(`/api/enfermagem/chamados?${params.toString()}`);
      chamados = dados;
    } catch (e) {
      if (!ultimaListaConhecida.length) {
        lista.innerHTML = `<div class="estado-vazio">Não foi possível carregar os chamados. Verifique sua conexão.</div>`;
      }
      return;
    }

    ultimaListaConhecida = chamados;
    if (!detectorLista(chamados)) return; // nada mudou desde o último ciclo — evita re-render/flicker

    renderLista(chamados);
    if (chamadoAbertoId) {
      const atualizado = chamados.find((c) => c.id === chamadoAbertoId);
      if (atualizado) renderModal(atualizado);
      else if (!filtros.status) fecharModal(); // finalizado por outro profissional
    }
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
      elCard.addEventListener("click", () => abrirModal(parseInt(elCard.dataset.id, 10), chamados));
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
          ${seloTempoEspera(c)}
        </div>
      </button>
    `;
  }

  // ---------------------------------------------------------------------
  // Modal (detalhe + ações)
  // ---------------------------------------------------------------------
  function abrirModal(id, chamadosConhecidos) {
    chamadoAbertoId = id;
    fundoModal.classList.add("aberto");
    const chamado = (chamadosConhecidos || []).find((c) => c.id === id);
    if (chamado) renderModal(chamado);
  }

  function fecharModal() {
    fundoModal.classList.remove("aberto");
    chamadoAbertoId = null;
  }

  function renderModal(c) {
    const acoes = [];
    if (c.status === "pendente") {
      acoes.push(`<button class="botao botao-primario botao-bloco" id="botaoAssumir">Assumir chamado</button>`);
    }
    if (c.status === "em_atendimento") {
      acoes.push(`<button class="botao botao-sucesso botao-bloco" id="botaoFinalizar">Finalizar atendimento</button>`);
      acoes.push(`<p class="texto-suave" id="avisoTempoMinimo" style="margin:6px 0 0;font-size:.85rem;" hidden></p>`);
    }

    modalChamado.innerHTML = `
      <div class="modal-topo-admin">
        <div>
          <h2>Leito ${escapeHtml(c.leito)}</h2>
          <span class="selo-prioridade selo-${c.prioridade}">${c.prioridade_emoji} ${c.prioridade_label}</span>
          ${c.acima_do_tempo_esperado ? `<span class="selo-atrasado" style="margin-left:6px;">Acima do tempo esperado</span>` : ""}
        </div>
        <button class="fechar-modal" id="botaoFecharModal" aria-label="Fechar">✕</button>
      </div>
      <div class="bloco-info-admin">
        <div><b>Solicitação:</b> ${escapeHtml(c.categoria)} — ${escapeHtml(c.subcategoria)}</div>
        ${c.detalhe ? `<div><b>Detalhe:</b> ${escapeHtml(c.detalhe)}</div>` : ""}
        <div><b>Status:</b> ${escapeHtml(c.status_label)}</div>
        <div><b>Aberto em:</b> ${c.criado_em}</div>
        ${c.inicio_atendimento ? `<div><b>Assumido em:</b> ${c.inicio_atendimento}</div>` : ""}
        ${c.finalizado_em ? `<div><b>Finalizado em:</b> ${c.finalizado_em}</div>` : ""}
        <div><b>Tempo de espera:</b> ${seloTempoEspera(c)}</div>
        ${c.tempo_atendimento_min != null ? `<div><b>Tempo de atendimento:</b> ${formatarMinutos(c.tempo_atendimento_min)}</div>` : ""}
        ${c.avaliacao != null ? `<div><b>Avaliação do paciente:</b> ${"★".repeat(c.avaliacao)}${"☆".repeat(5 - c.avaliacao)}</div>` : ""}
      </div>
      <div class="linha-acoes-admin">${acoes.join("")}</div>
    `;

    document.getElementById("botaoFecharModal").addEventListener("click", fecharModal);
    const btnAssumir = document.getElementById("botaoAssumir");
    if (btnAssumir) btnAssumir.addEventListener("click", () => HRG.comBotaoTravado(btnAssumir, () => assumir(c.id)));
    const btnFinalizar = document.getElementById("botaoFinalizar");
    if (btnFinalizar) {
      btnFinalizar.addEventListener("click", () => HRG.comBotaoTravado(btnFinalizar, () => finalizar(c.id)));
      iniciarContagemFinalizar(btnFinalizar, c.segundos_ate_finalizar || 0);
    }
  }

  // Tempo mínimo de atendimento (2 min): o botão "Finalizar" fica bloqueado
  // com contagem regressiva. O servidor é quem decide (devolve 409 se
  // tentarem antes), aqui é só a indicação visual.
  let timerFinalizar = null;
  function iniciarContagemFinalizar(botao, restante) {
    clearInterval(timerFinalizar);
    const aviso = document.getElementById("avisoTempoMinimo");
    const fim = Date.now() + restante * 1000;
    const atualizar = () => {
      const seg = Math.ceil((fim - Date.now()) / 1000);
      if (!document.body.contains(botao)) { clearInterval(timerFinalizar); return; }
      if (seg > 0) {
        botao.disabled = true;
        botao.textContent = `Finalizar atendimento (${Math.floor(seg / 60)}:${String(seg % 60).padStart(2, "0")})`;
        if (aviso) { aviso.hidden = false; aviso.textContent = "Tempo mínimo de atendimento: 2 minutos após assumir o chamado."; }
      } else {
        clearInterval(timerFinalizar);
        botao.disabled = false;
        botao.textContent = "Finalizar atendimento";
        if (aviso) aviso.hidden = true;
      }
    };
    atualizar();
    if (restante > 0) timerFinalizar = setInterval(atualizar, 1000);
  }

  async function assumir(id) {
    try {
      await HRG.fetchJSON(`/api/enfermagem/chamados/${id}/assumir`, { method: "POST" });
      HRG.toast("Chamado assumido.", "sucesso");
      await carregarTudo();
    } catch (err) {
      HRG.toast(err.message, "erro");
    }
  }

  async function finalizar(id) {
    try {
      await HRG.fetchJSON(`/api/enfermagem/chamados/${id}/finalizar`, { method: "POST" });
      // Finalizado = sai da Central (vai para o Histórico): fecha o
      // detalhe na hora, sem o profissional precisar clicar em "✕".
      fecharModal();
      HRG.toast("Atendimento finalizado.", "sucesso");
      await carregarTudo();
    } catch (err) {
      HRG.toast(err.message, "erro");
    }
  }

  async function carregarTudo() {
    // Depois de assumir/finalizar, os dados realmente mudaram no servidor —
    // o detector de mudança em carregarLista() já percebe isso sozinho
    // (o JSON vindo do servidor é diferente do anterior) e re-renderiza.
    await Promise.all([carregarStats(), carregarLista()]);
  }

  // ---------------------------------------------------------------------
  // Filtros ativos (chips com "×") — reflete o painel avançado + busca.
  // ---------------------------------------------------------------------
  function limparFiltros() {
    filtroBusca.value = ""; filtroAndar.value = ""; filtroLeito.value = "";
    filtroCategoria.value = ""; filtroPeriodo.value = ""; filtroOrdenar.value = "prioridade";
    delete filtros.q; delete filtros.andar; delete filtros.leito;
    delete filtros.categoria; delete filtros.periodo; filtros.ordenar = "";
    renderFiltrosAtivos();
    carregarLista();
  }

  function renderFiltrosAtivos() {
    const rotulos = {
      q: (v) => `Busca: "${v}"`,
      andar: () => `Andar: ${filtroAndar.selectedOptions[0].textContent}`,
      leito: (v) => `Leito: ${v}`,
      categoria: (v) => `Tipo: ${v}`,
      periodo: (v) => ({ hoje: "Hoje", "7dias": "Últimos 7 dias", "30dias": "Últimos 30 dias" }[v] || v),
      ordenar: (v) => (v && v !== "prioridade" ? `Ordenar: ${v === "recentes" ? "Mais recentes" : "Mais antigos"}` : null),
    };
    const camposLimpos = {
      q: () => { filtroBusca.value = ""; delete filtros.q; },
      andar: () => { filtroAndar.value = ""; delete filtros.andar; },
      leito: () => { filtroLeito.value = ""; delete filtros.leito; },
      categoria: () => { filtroCategoria.value = ""; delete filtros.categoria; },
      periodo: () => { filtroPeriodo.value = ""; delete filtros.periodo; },
      ordenar: () => { filtroOrdenar.value = "prioridade"; filtros.ordenar = ""; },
    };

    const ativos = Object.keys(rotulos).filter((chave) => filtros[chave]);
    if (!ativos.length) { filtrosAtivosEl.innerHTML = ""; return; }

    filtrosAtivosEl.innerHTML = ativos.map((chave) => {
      const texto = rotulos[chave](filtros[chave]);
      if (!texto) return "";
      return `<span class="filtro-ativo-chip" data-chave="${chave}">${escapeHtml(texto)}<button type="button" aria-label="Remover filtro">✕</button></span>`;
    }).join("");

    filtrosAtivosEl.querySelectorAll(".filtro-ativo-chip button").forEach((botao) => {
      botao.addEventListener("click", () => {
        const chave = botao.parentElement.dataset.chave;
        if (camposLimpos[chave]) camposLimpos[chave]();
        renderFiltrosAtivos();
        carregarLista();
      });
    });
  }

  // ---------------------------------------------------------------------
  // Ligações de filtro
  // ---------------------------------------------------------------------
  chipsStatus.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      chipsStatus.querySelectorAll(".chip").forEach((c) => c.classList.remove("ativo"));
      chip.classList.add("ativo");
      filtros.status = chip.dataset.status;
      carregarLista();
    });
  });

  chipsPrioridade.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      chipsPrioridade.querySelectorAll(".chip").forEach((c) => c.classList.remove("ativo"));
      chip.classList.add("ativo");
      filtros.prioridade = chip.dataset.prioridade;
      carregarLista();
    });
  });

  botaoFiltrosAvancados.addEventListener("click", () => {
    const abrir = painelFiltrosAvancados.hidden;
    painelFiltrosAvancados.hidden = !abrir;
    botaoFiltrosAvancados.setAttribute("aria-expanded", String(abrir));
  });

  filtroAndar.addEventListener("change", () => { filtros.andar = filtroAndar.value; renderFiltrosAtivos(); carregarLista(); });
  filtroCategoria.addEventListener("change", () => { filtros.categoria = filtroCategoria.value; renderFiltrosAtivos(); carregarLista(); });
  filtroPeriodo.addEventListener("change", () => { filtros.periodo = filtroPeriodo.value; renderFiltrosAtivos(); carregarLista(); });
  filtroOrdenar.addEventListener("change", () => { filtros.ordenar = filtroOrdenar.value; renderFiltrosAtivos(); carregarLista(); });
  filtroLeito.addEventListener("input", HRG.debounce(() => {
    filtros.leito = filtroLeito.value.trim();
    renderFiltrosAtivos();
    carregarLista();
  }, 350));
  filtroBusca.addEventListener("input", HRG.debounce(() => {
    filtros.q = filtroBusca.value.trim();
    renderFiltrosAtivos();
    carregarLista();
  }, 350));

  botaoLimparFiltros.addEventListener("click", limparFiltros);

  fundoModal.addEventListener("click", (e) => { if (e.target === fundoModal) fecharModal(); });
  HRG.fecharComEsc(() => fundoModal.classList.contains("aberto"), fecharModal);

  // ---------------------------------------------------------------------
  // Atualização em quase tempo real por polling. O tempo de espera de
  // cada chamado avança sozinho (e pode cruzar o SLA da faixa), então a
  // lista precisa ser reconsultada periodicamente mesmo sem nenhuma ação
  // nova de ninguém. Pausa quando a aba não está visível.
  // ---------------------------------------------------------------------
  HRG.pollWhileVisible(carregarTudo, 5000);
})();
