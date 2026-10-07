(function () {
  "use strict";

  // Mesmo padrão visual (e mesma estrutura de HTML/CSS) da tela de
  // acompanhamento de pedidos da Hotelaria — ver static/js/hotelaria/acompanhar.js
  // (renderStatus / renderAreaAvaliacao). Estilos em base.css.
  const tela = document.getElementById("telaAcompanhar");
  const subtitulo = document.getElementById("subtituloAcompanhar");
  const chamadoId = window.CHAMADO_ID;
  const escapeHtml = HRG.escapeHtml;
  let chamado = null;
  let estrelasSelecionadas = 0;
  let enviandoAvaliacao = false;
  let falhasSeguidas = 0;
  const detectorEstado = HRG.criarDetectorDeMudanca();

  const PASSOS = [
    { chave: "pendente", rotulo: "Recebido" },
    { chave: "em_atendimento", rotulo: "Em atendimento" },
    { chave: "finalizado", rotulo: "Finalizado" },
  ];
  const ROTULO_STATUS = { pendente: "Pendente", em_atendimento: "Em atendimento", finalizado: "Finalizado" };
  // Classe do selo grande: mesmas cores da Hotelaria ("em_andamento" lá é o
  // equivalente de "em_atendimento" aqui).
  const CLASSE_STATUS = { pendente: "pendente", em_atendimento: "em_andamento", finalizado: "finalizado" };

  const ICONE_CHECK = '<svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  async function buscar() {
    try {
      const { dados } = await HRG.fetchJSON(`/api/enfermagem/chamados/${chamadoId}`);
      falhasSeguidas = 0;
      return dados;
    } catch (err) {
      falhasSeguidas += 1;
      if (err.status === 404) {
        tela.innerHTML = `<p class="texto-carregando">Chamado não encontrado.</p>`;
      } else if (!chamado) {
        // Primeira carga já falhou por rede — não há nada anterior pra
        // manter na tela, então mostra um estado dedicado em vez de deixar
        // a tela em branco.
        tela.innerHTML = `<p class="texto-carregando">Não foi possível carregar o chamado. Verifique sua conexão.</p>`;
      } else if (falhasSeguidas >= 2) {
        // Já havia um chamado carregado: mantém a última tela conhecida,
        // só avisa que a atualização está falhando.
        mostrarAvisoSemConexao(true);
      }
      return null;
    }
  }

  function mostrarAvisoSemConexao(mostrar) {
    const aviso = document.getElementById("avisoSemConexao");
    if (aviso) aviso.hidden = !mostrar;
  }

  function trilhaHtml() {
    const ordemAtual = PASSOS.findIndex((p) => p.chave === chamado.status);
    return PASSOS.map((p, i) => {
      let classe = "";
      if (i < ordemAtual) classe = "concluido";
      else if (i === ordemAtual) classe = "ativo";
      const numero = i < ordemAtual ? "✓" : i + 1;
      const linha = i < PASSOS.length - 1
        ? `<div class="linha-status ${i < ordemAtual ? "preenchida" : ""}"></div>`
        : "";
      return `
        <div class="passo-status ${classe}">
          <div class="bola">${numero}</div>
          <span class="rotulo-passo">${p.rotulo}</span>
        </div>
        ${linha}
      `;
    }).join("");
  }

  function render() {
    if (!chamado) return;
    subtitulo.textContent = `${chamado.categoria} · Leito ${chamado.leito}`;

    tela.innerHTML = `
      <p id="avisoSemConexao" class="banner-status banner-status-sem_conexao" hidden style="margin-bottom:12px;">
        <span class="banner-status-icone">📶</span>
        <span>Sem conexão no momento — mostrando os últimos dados recebidos.</span>
      </p>
      <div class="cartao-status surgir">
        <span class="selo-status-grande ${CLASSE_STATUS[chamado.status] || "pendente"}">${ROTULO_STATUS[chamado.status] || escapeHtml(chamado.status)}</span>
        <div class="trilha-status">${trilhaHtml()}</div>
        <div class="resumo-chamado">
          <div><b>Categoria:</b> ${escapeHtml(chamado.categoria)}</div>
          <div><b>Solicitação:</b> ${escapeHtml(chamado.subcategoria)}</div>
          ${chamado.detalhe ? `<div><b>Detalhe:</b> ${escapeHtml(chamado.detalhe)}</div>` : ""}
          <div><b>Aberto em:</b> ${chamado.criado_em}</div>
        </div>
      </div>

      <div id="areaAvaliacao"></div>
    `;

    renderAvaliacao();
  }

  function renderAvaliacao() {
    const area = document.getElementById("areaAvaliacao");
    if (!area) return;
    if (chamado.status !== "finalizado") { area.innerHTML = ""; return; }

    if (chamado.avaliacao != null) {
      area.innerHTML = `
        <div class="mensagem-agradecimento surgir">
          <div class="icone-check">${ICONE_CHECK}</div>
          <h3>Obrigado pela sua avaliação!</h3>
          <p style="color:var(--texto-suave);">Seu feedback ajuda a melhorar nosso atendimento.</p>
          <a class="botao largo" href="${urlNovaSolicitacao()}" style="margin-top:8px;">Nova solicitação</a>
        </div>
      `;
      return;
    }

    const estrelasHtml = [1, 2, 3, 4, 5].map((n) => `<button type="button" data-n="${n}" aria-label="${n} estrela${n > 1 ? "s" : ""}">★</button>`).join("");
    area.innerHTML = `
      <div class="caixa-avaliacao surgir">
        <h3 style="margin:0;">Como foi o atendimento?</h3>
        <div class="estrelas" id="estrelasAvaliacao">${estrelasHtml}</div>
        <textarea id="comentarioAvaliacao" maxlength="300" placeholder="Comentário (opcional)" aria-label="Comentário sobre o atendimento"></textarea>
        <button class="botao largo" id="botaoEnviarAvaliacao" style="margin-top:12px;">Enviar avaliação</button>
      </div>
    `;

    const botoes = area.querySelectorAll("#estrelasAvaliacao button");
    botoes.forEach((b) => {
      b.addEventListener("click", () => {
        estrelasSelecionadas = parseInt(b.dataset.n, 10);
        botoes.forEach((x) => x.classList.toggle("ativa", parseInt(x.dataset.n, 10) <= estrelasSelecionadas));
      });
    });

    document.getElementById("botaoEnviarAvaliacao").addEventListener("click", enviarAvaliacao);
  }

  // Volta à seleção de ocorrências do MESMO leito do chamado.
  function urlNovaSolicitacao() {
    const params = new URLSearchParams({ andar: chamado.andar, leito: chamado.leito });
    return `/enfermagem/?${params.toString()}`;
  }

  function novaSolicitacao() {
    window.location.href = urlNovaSolicitacao();
  }

  async function enviarAvaliacao() {
    if (enviandoAvaliacao) return;
    if (estrelasSelecionadas < 1) {
      HRG.toast("A avaliação é obrigatória: selecione de 1 a 5 estrelas.", "info");
      return;
    }
    enviandoAvaliacao = true;
    const comentario = document.getElementById("comentarioAvaliacao").value.trim();
    const botao = document.getElementById("botaoEnviarAvaliacao");
    await HRG.comBotaoTravado(botao, async () => {
      try {
        const { dados } = await HRG.fetchJSON(`/api/enfermagem/chamados/${chamadoId}/avaliar`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ avaliacao: estrelasSelecionadas, comentario }),
        });
        chamado = dados;
        detectorEstado(snapshot(chamado));
        // Avaliou: libera o dispositivo e volta à seleção de novas demandas
        // do mesmo leito.
        try { localStorage.removeItem("rg_enfermagem_chamado_ativo"); } catch (e) {}
        renderAvaliacao();
        setTimeout(novaSolicitacao, 2500);
      } catch (err) {
        HRG.toast(err.message, "erro");
      }
    });
    enviandoAvaliacao = false;
  }

  function snapshot(c) {
    return `${c.status}|${c.avaliacao}|${c.detalhe}`;
  }

  // Atualização em quase tempo real por polling — sem depender de nenhuma
  // biblioteca externa de WebSocket. Pausa quando a aba não está visível.
  // Só redesenha quando algo visível mudou (status/avaliação), para não
  // apagar as estrelas/comentário que o paciente estiver preenchendo.
  HRG.pollWhileVisible(async () => {
    const dados = await buscar();
    if (dados) {
      chamado = dados;
      mostrarAvisoSemConexao(false);
      if (detectorEstado(snapshot(chamado))) render();
    }
  }, 5000);
})();
