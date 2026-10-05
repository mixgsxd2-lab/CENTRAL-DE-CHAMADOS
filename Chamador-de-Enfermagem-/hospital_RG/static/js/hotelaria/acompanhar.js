(function () {
  "use strict";

  // Acompanhamento, pelo paciente, de um pedido de Hotelaria (criado pela
  // categoria "Outros" da área do paciente da Enfermagem). A antiga tela
  // /hotelaria/paciente deixou de existir: o paciente entra e sai sempre
  // pela área do paciente da Enfermagem (/enfermagem/).
  const tela = document.getElementById("telaAcompanhar");
  const subtitulo = document.getElementById("subtituloAcompanhar");
  const chamadoId = window.CHAMADO_ID;
  const escapeHtml = HRG.escapeHtml;
  const LS_KEY = "rg_hospital_chamado_ativo";
  const URL_INICIO = "/enfermagem/";

  let chamado = null;
  let estrelasSelecionadas = 0;
  let enviandoAvaliacao = false;
  let falhasSeguidas = 0;
  const detectorEstado = HRG.criarDetectorDeMudanca();

  const PASSOS = [
    { chave: "pendente", rotulo: "Recebido" },
    { chave: "em_andamento", rotulo: "Em andamento" },
    { chave: "finalizado", rotulo: "Finalizado" },
  ];
  const ROTULO_STATUS = { pendente: "Pendente", em_andamento: "Em andamento", finalizado: "Finalizado" };

  const ICONE_CHECK = '<svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  async function buscar() {
    try {
      const { dados } = await HRG.fetchJSON(`/hotelaria/api/chamados/${chamadoId}`);
      falhasSeguidas = 0;
      return dados;
    } catch (err) {
      falhasSeguidas += 1;
      if (err.status === 404) {
        tela.innerHTML = `<p class="texto-carregando">Chamado não encontrado.</p>`;
      } else if (!chamado) {
        tela.innerHTML = `<p class="texto-carregando">Não foi possível carregar o chamado. Verifique sua conexão.</p>`;
      } else if (falhasSeguidas >= 2) {
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
    subtitulo.textContent = `${chamado.servico_nome} · Leito ${chamado.leito}`;

    tela.innerHTML = `
      <p id="avisoSemConexao" class="banner-status banner-status-sem_conexao" hidden style="margin-bottom:12px;">
        <span class="banner-status-icone">📶</span>
        <span>Sem conexão no momento — mostrando os últimos dados recebidos.</span>
      </p>
      <div class="cartao-status surgir">
        <span class="selo-status-grande ${chamado.status}">${ROTULO_STATUS[chamado.status] || escapeHtml(chamado.status)}</span>
        <div class="trilha-status">${trilhaHtml()}</div>
        <div class="resumo-chamado">
          <div><b>Serviço:</b> ${escapeHtml(chamado.servico_nome)}</div>
          <div><b>Solicitação:</b> ${escapeHtml(chamado.descricao_exibicao || chamado.descricao)}</div>
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

    if (chamado.tem_avaliacao) {
      area.innerHTML = `
        <div class="mensagem-agradecimento surgir">
          <div class="icone-check">${ICONE_CHECK}</div>
          <h3>Obrigado pela sua avaliação!</h3>
          <p style="color:var(--texto-suave);">Seu feedback ajuda a melhorar nosso atendimento.</p>
          <a class="botao largo" href="${URL_INICIO}" id="linkNovoChamado" style="margin-top:16px;">Voltar ao início</a>
        </div>
      `;
      document.getElementById("linkNovoChamado").addEventListener("click", liberarDispositivo);
      return;
    }

    const estrelasHtml = [1, 2, 3, 4, 5].map((n) => `<button type="button" data-n="${n}" aria-label="${n} estrela${n > 1 ? "s" : ""}">★</button>`).join("");
    area.innerHTML = `
      <div class="caixa-avaliacao surgir">
        <h3 style="margin:0;">Como foi o atendimento?</h3>
        <div class="estrelas" id="estrelasAvaliacao">${estrelasHtml}</div>
        <textarea id="comentarioAvaliacao" maxlength="300" placeholder="Comentário (opcional)" aria-label="Comentário sobre o atendimento"></textarea>
        <button class="botao largo" id="botaoEnviarAvaliacao" style="margin-top:12px;">Enviar avaliação</button>
        <button class="botao secundario largo" id="botaoSairSemAvaliar" style="margin-top:8px;">Sair sem avaliar</button>
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
    document.getElementById("botaoSairSemAvaliar").addEventListener("click", sairSemAvaliar);
  }

  function liberarDispositivo() {
    try { localStorage.removeItem(LS_KEY); } catch (e) {}
  }

  // "Sair sem avaliar": libera o dispositivo (só remove a referência local do
  // chamado — o chamado continua salvo no servidor) e volta para a área do
  // paciente da Enfermagem, pronta para um novo chamado.
  function sairSemAvaliar() {
    liberarDispositivo();
    window.location.href = URL_INICIO;
  }

  async function enviarAvaliacao() {
    if (enviandoAvaliacao) return;
    if (estrelasSelecionadas < 1) {
      HRG.toast("Selecione de 1 a 5 estrelas, ou apenas ignore — a avaliação é opcional.", "info");
      return;
    }
    enviandoAvaliacao = true;
    const comentario = document.getElementById("comentarioAvaliacao").value.trim();
    const botao = document.getElementById("botaoEnviarAvaliacao");
    await HRG.comBotaoTravado(botao, async () => {
      try {
        await HRG.fetchJSON(`/hotelaria/api/chamados/${chamadoId}/avaliacao`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ estrelas: estrelasSelecionadas, comentario }),
        });
        chamado.tem_avaliacao = true;
        detectorEstado(snapshot(chamado));
        renderAvaliacao();
      } catch (err) {
        HRG.toast(err.message, "erro");
      }
    });
    enviandoAvaliacao = false;
  }

  function snapshot(c) {
    return `${c.status}|${c.tem_avaliacao}`;
  }

  // Atualização em quase tempo real por polling; só redesenha quando algo
  // visível mudou, para não apagar as estrelas/comentário em preenchimento.
  HRG.pollWhileVisible(async () => {
    const dados = await buscar();
    if (dados) {
      chamado = dados;
      mostrarAvisoSemConexao(false);
      if (detectorEstado(snapshot(chamado))) render();
    }
  }, 4000);
})();
