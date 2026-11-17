(function () {
  "use strict";

  /* ==========================================================================
     Fluxo do paciente (QR Code do leito)

       1. Início ............ Enfermagem  |  Hotelaria
       2. Enfermagem ........ Urgência / Dor / Soro / Falar com Enfermagem
       3. Opções ............ subopções da categoria (ou serviços de Hotelaria)
       4. Confirmação ....... resumo + envio

     Todas as telas usam o MESMO cartão (`.cartao-opcao`: emoji + título +
     dica), para que Urgência, Dor, Soro, Falar com Enfermagem e Hotelaria
     tenham exatamente o mesmo desenho.

     O paciente pode ter UM chamado de Enfermagem e UM de Hotelaria abertos
     ao mesmo tempo. Enquanto um deles está em andamento, o cartão daquela
     área fica cinza na tela inicial e passa a levar ao acompanhamento — o
     estado vem do servidor (/api/enfermagem/paciente/chamados-ativos),
     nunca do navegador, então vale para qualquer celular no mesmo leito.
     ========================================================================== */

  // Os pedidos de Hotelaria continuam usando, no backend, a categoria
  // "Outros" de enfermagem/constants.py (cada opção mapeia 1:1 para um
  // serviço da Central de Hotelaria) — só deixou de aparecer como categoria.
  const CATEGORIA_HOTELARIA = "Outros";

  const AREAS = {
    enfermagem: { tom: "primaria", emoji: "👩‍⚕️", titulo: "Enfermagem", dica: "Urgência, dor, soro ou falar com a equipe" },
    hotelaria: { tom: "hotelaria", emoji: "🛎️", titulo: "Hotelaria", dica: "Quarto, alimentação, enxoval, manutenção e limpeza" },
  };

  const EMOJI_CATEGORIA = {
    "Urgência": { tom: "critica", emoji: "🚨", dica: "Preciso de ajuda agora" },
    "Dor": { tom: "critica", emoji: "😣", dica: "Estou sentindo dor" },
    "Soro": { tom: "media", emoji: "💧", dica: "Problema com o soro ou acesso" },
    "Falar com Enfermagem": { tom: "baixa", emoji: "💬", dica: "Dúvidas e orientações" },
  };

  // `tom` = cor do cartão, a mesma do design anterior: representa o estado
  // do paciente (vermelho = crítico, laranja/amarelo = intermediário,
  // verde = tranquilo, cinza = neutro, roxo = Hotelaria). Segue as faixas do
  // motor de prioridade (enfermagem/priority.py::_tier).
  // Emoji + dica curta de cada subopção. A chave é o texto exato da opção em
  // enfermagem/constants.py (o que é gravado no chamado).
  const OPCOES_VISUAIS = {
    "Urgência": {
      "Não consigo respirar bem": { tom: "critica", emoji: "😰", dica: "Dificuldade para respirar" },
      "Sangramento intenso": { tom: "critica", emoji: "🩸", dica: "Sangramento visível" },
      "Queda ou acidente no quarto": { tom: "critica", emoji: "🤕", dica: "Você caiu ou se machucou" },
      "Confusão mental ou desmaio": { tom: "critica", emoji: "😵", dica: "Perda de consciência ou confusão" },
      "Dor súbita e muito intensa": { tom: "critica", emoji: "😖", dica: "Dor forte que começou de repente" },
      "Outra emergência": { tom: "critica", emoji: "🚨", dica: "Qualquer outra situação grave" },
    },
    "Dor": {
      "Dor no peito": { tom: "critica", emoji: "🥵", dica: "Aperto no peito ou falta de ar" },
      "Dor muito forte": { tom: "laranja", emoji: "😖", dica: "Difícil de aguentar" },
      "Dor moderada": { tom: "amarelo", emoji: "😣", dica: "Incomoda, mas dá pra aguentar" },
      "Dor leve": { tom: "verde", emoji: "🙂", dica: "Pequena, quase não atrapalha" },
    },
    "Soro": {
      "Está retornando sangue": { tom: "vermelho", emoji: "🩸", dica: "Sangue voltando pelo equipo" },
      "Problema no acesso": { tom: "laranja", emoji: "⚠️", dica: "Acesso solto, dolorido ou vazando" },
      "Acabou": { tom: "verde", emoji: "💧", dica: "O soro do frasco já terminou" },
      "Está perto do fim": { tom: "verde", emoji: "⏳", dica: "Ainda dá tempo, mas já avise a equipe" },
      "Outro problema": { tom: "media", emoji: "❓", dica: "Qualquer outra dificuldade com o soro" },
    },
    "Falar com Enfermagem": {
      "Dúvida sobre medicação": { tom: "baixa", emoji: "💊", dica: "Perguntas sobre remédios" },
      "Dúvida sobre procedimento ou alta": { tom: "baixa", emoji: "📋", dica: "Exames, alta ou rotina" },
      "Preciso de orientação": { tom: "baixa", emoji: "🧭", dica: "Qualquer orientação da equipe" },
      "Assunto geral": { tom: "baixa", emoji: "💬", dica: "Outro assunto não urgente" },
    },
    [CATEGORIA_HOTELARIA]: {
      "Acomodação (cama, travesseiro, TV, ar-condicionado)": { tom: "hotelaria", emoji: "🛏️", titulo: "Acomodação", dica: "Cama, travesseiro, TV ou ar-condicionado" },
      "Alimentação": { tom: "hotelaria", emoji: "🍽️", dica: "Refeição, lanche ou dieta especial" },
      "Roupa de cama / Enxoval": { tom: "hotelaria", emoji: "🧺", dica: "Lençol, cobertor ou toalhas" },
      "Manutenção do quarto": { tom: "hotelaria", emoji: "🔧", dica: "Chuveiro, luz, parte elétrica ou hidráulica" },
      "Limpeza do quarto ou banheiro": { tom: "hotelaria", emoji: "🧹", dica: "Limpeza ou higienização" },
    },
  };

  const ICONE_CHECK = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  const ICONE_ENCAMINHADO = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>';

  const CATEGORIAS_ENFERMAGEM = Object.keys(window.CATEGORIAS || {}).filter((n) => n !== CATEGORIA_HOTELARIA);
  // "Falar com Enfermagem" é a única categoria sem passo de confirmação:
  // o chamado é criado assim que o paciente toca em "Selecionar".
  const CATEGORIA_ENVIO_DIRETO = "Falar com Enfermagem";

  const URL_ACOMPANHAR = {
    enfermagem: (id) => `/enfermagem/acompanhar/${id}`,
    hotelaria: (id) => `/enfermagem/acompanhar-hotelaria/${id}`,
  };

  const el = {
    tela: document.getElementById("telaPaciente"),
    barra: document.getElementById("barraInferior"),
    botaoVoltar: document.getElementById("botaoVoltar"),
    marca: document.getElementById("marcaPaciente"),
    trilha: document.querySelectorAll("#trilhaPassos span"),
  };

  const state = {
    andar: "",
    leito: "",
    area: "",
    categoria: "",
    subcategoria: "",
  };

  const escapeHtml = HRG.escapeHtml;

  function labelAndar(andar) {
    return (andar || "").replace(/\s*—\s*LEITOS\s*$/i, "");
  }

  function definirPasso(numero, { voltar = null, marca = "Hospital Rio Grande", semBarra = false } = {}) {
    el.trilha.forEach((span) => {
      span.classList.toggle("ativo", parseInt(span.dataset.passo, 10) <= numero);
    });
    el.botaoVoltar.style.visibility = voltar ? "visible" : "hidden";
    el.botaoVoltar.onclick = voltar;
    el.marca.textContent = marca;
    el.tela.classList.toggle("tela-sem-barra", semBarra);
    el.tela.classList.remove("tela-barra-dupla");
    if (semBarra) el.barra.innerHTML = "";
    window.scrollTo(0, 0);
  }

  function marcaArea() {
    return state.area === "hotelaria" ? "Hotelaria" : "Enfermagem";
  }

  // Cartão padrão usado em TODAS as telas de escolha.
  function cartaoHtml({ emoji, titulo, dica, tom = "", attrs = "", classe = "", selo = "" }) {
    return `
      <button type="button" class="cartao-opcao${tom ? ` tom-${tom}` : ""} ${classe}" ${attrs}>
        <span class="emoji-opcao" aria-hidden="true">${emoji || "•"}</span>
        <span class="texto-opcao">
          <strong>${escapeHtml(titulo)}</strong>
          ${dica ? `<small>${escapeHtml(dica)}</small>` : ""}
          ${selo}
        </span>
      </button>
    `;
  }

  // -------------------------------------------------------------------
  // Passo 1: Enfermagem | Hotelaria
  // -------------------------------------------------------------------
  async function renderInicio() {
    definirPasso(1, { semBarra: true });
    state.area = state.categoria = state.subcategoria = "";

    let ativos = { enfermagem: null, hotelaria: null };
    try {
      const { dados } = await HRG.fetchJSON("/api/enfermagem/paciente/chamados-ativos", { cache: "no-store" });
      ativos = dados;
    } catch (err) {
      if (err.dados && err.dados.acesso_expirado && window.HRGAcessoPaciente) {
        window.HRGAcessoPaciente.mostrarExpirado();
        return;
      }
    }

    const cartoes = Object.entries(AREAS).map(([chave, area]) => {
      const ativo = ativos[chave];
      return cartaoHtml({
        emoji: area.emoji,
        tom: area.tom,
        titulo: area.titulo,
        dica: ativo ? "Você já tem um chamado aqui. Toque para acompanhar." : area.dica,
        classe: `cartao-area${ativo ? " em-andamento" : ""}`,
        attrs: `data-area="${chave}"${ativo ? ` data-chamado="${ativo.id}" aria-label="${area.titulo}: chamado em andamento, toque para acompanhar"` : ""}`,
        selo: ativo ? `<span class="selo-andamento">⏳ Chamado em andamento</span>` : "",
      });
    }).join("");

    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>Como podemos ajudar?</h1>
        <p>Leito ${escapeHtml(state.leito)} · ${escapeHtml(labelAndar(state.andar))}</p>
      </div>
      <div class="grade-areas surgir">${cartoes}</div>
    `;

    el.tela.querySelectorAll(".cartao-area").forEach((botao) => {
      botao.addEventListener("click", () => {
        const area = botao.dataset.area;
        if (botao.dataset.chamado) {
          window.location.href = URL_ACOMPANHAR[area](botao.dataset.chamado);
          return;
        }
        state.area = area;
        if (area === "hotelaria") {
          state.categoria = CATEGORIA_HOTELARIA;
          renderOpcoes();
        } else {
          renderCategorias();
        }
      });
    });
  }

  // -------------------------------------------------------------------
  // Passo 2 (Enfermagem): categorias
  // -------------------------------------------------------------------
  function renderCategorias() {
    definirPasso(2, { voltar: renderInicio, marca: "Enfermagem", semBarra: true });
    state.categoria = state.subcategoria = "";

    const cartoes = CATEGORIAS_ENFERMAGEM.map((nome) => {
      const v = EMOJI_CATEGORIA[nome] || {};
      return cartaoHtml({ emoji: v.emoji, tom: v.tom, titulo: nome, dica: v.dica, attrs: `data-categoria="${escapeHtml(nome)}"` });
    }).join("");

    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>Enfermagem</h1>
        <p>Qual é o motivo do chamado?</p>
      </div>
      <div class="lista-opcoes surgir">${cartoes}</div>
    `;

    el.tela.querySelectorAll(".cartao-opcao").forEach((botao) => {
      botao.addEventListener("click", () => {
        state.categoria = botao.dataset.categoria;
        renderOpcoes();
      });
    });
  }

  // -------------------------------------------------------------------
  // Passo 3: opções da categoria (ou serviços de Hotelaria)
  // -------------------------------------------------------------------
  function renderOpcoes() {
    const eHotelaria = state.area === "hotelaria";
    const envioDireto = state.categoria === CATEGORIA_ENVIO_DIRETO;
    definirPasso(eHotelaria ? 2 : 3, { voltar: eHotelaria ? renderInicio : renderCategorias, marca: marcaArea() });
    state.subcategoria = "";

    const dados = window.CATEGORIAS[state.categoria];
    const visuais = OPCOES_VISUAIS[state.categoria] || {};
    const cartoes = dados.opcoes.map((texto) => {
      const v = visuais[texto] || {};
      return cartaoHtml({ emoji: v.emoji, tom: v.tom, titulo: v.titulo || texto, dica: v.dica, attrs: `data-opcao="${escapeHtml(texto)}"` });
    }).join("");

    const titulo = eHotelaria ? "Hotelaria" : state.categoria;
    const subtitulo = eHotelaria
      ? "Do que você precisa?"
      : (envioDireto ? "Escolha o assunto — o chamado é enviado na hora" : "Escolha a opção que melhor descreve a situação");

    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>${escapeHtml(titulo)}</h1>
        <p>${escapeHtml(subtitulo)}</p>
      </div>
      <div class="lista-opcoes surgir">${cartoes}</div>
    `;

    const rotulo = envioDireto ? "Selecionar" : "Continuar";
    el.barra.innerHTML = `<button class="botao botao-primario botao-bloco" id="botaoAvancar" disabled>${rotulo}</button>`;
    const botaoAvancar = document.getElementById("botaoAvancar");

    const cartoesEl = el.tela.querySelectorAll(".cartao-opcao");
    cartoesEl.forEach((botao) => {
      botao.addEventListener("click", () => {
        cartoesEl.forEach((b) => b.classList.remove("selecionada"));
        botao.classList.add("selecionada");
        state.subcategoria = botao.dataset.opcao;
        botaoAvancar.disabled = false;
      });
    });

    botaoAvancar.addEventListener("click", () => {
      if (!state.subcategoria) return;
      if (!envioDireto) { renderConfirmar(); return; }
      botaoAvancar.disabled = true;
      botaoAvancar.textContent = "Enviando...";
      cartoesEl.forEach((b) => { b.disabled = true; });
      enviarChamado();
    });
  }

  // -------------------------------------------------------------------
  // Passo 4: resumo + envio
  // -------------------------------------------------------------------
  function renderConfirmar() {
    definirPasso(4, { voltar: renderOpcoes, marca: marcaArea() });
    const v = (OPCOES_VISUAIS[state.categoria] || {})[state.subcategoria] || {};
    const motivo = state.area === "hotelaria" ? "Hotelaria" : state.categoria;
    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>Confirme seu chamado</h1>
        <p>Revise as informações antes de enviar</p>
      </div>
      <div class="cartao-passo surgir">
        <div class="resumo-linha"><span>Leito</span><b>${escapeHtml(state.leito)}</b></div>
        <div class="resumo-linha"><span>Andar</span><b>${escapeHtml(labelAndar(state.andar))}</b></div>
        <div class="resumo-linha"><span>Motivo</span><b>${escapeHtml(motivo)}</b></div>
        <div class="resumo-linha"><span>Solicitação</span><b>${v.emoji ? v.emoji + " " : ""}${escapeHtml(v.titulo || state.subcategoria)}</b></div>
      </div>
    `;
    el.barra.innerHTML = `<button class="botao botao-primario botao-bloco" id="botaoEnviar">Enviar chamado</button>`;
    document.getElementById("botaoEnviar").addEventListener("click", enviarChamado);
  }

  // Trava contra duplo-envio (o backend também protege — ver enfermagem/api.py).
  let enviandoChamado = false;

  async function enviarChamado() {
    if (enviandoChamado) return;
    enviandoChamado = true;

    const botao = document.getElementById("botaoEnviar");
    if (botao) {
      botao.disabled = true;
      botao.textContent = "Enviando...";
    }

    try {
      const { dados } = await HRG.fetchJSON("/api/enfermagem/chamados", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          andar: state.andar,
          leito: state.leito,
          categoria: state.categoria,
          subcategoria: state.subcategoria,
        }),
      });

      if (dados.duplicado) {
        // Já havia um chamado aberto nesta área (ex.: feito em outro
        // celular do mesmo leito) — leva direto ao acompanhamento dele.
        const area = dados.encaminhado_hotelaria ? "hotelaria" : "enfermagem";
        const id = dados.encaminhado_hotelaria ? dados.hotelaria_chamado_id : dados.id;
        HRG.toast("Você já tem um chamado em andamento.", "info");
        window.location.href = URL_ACOMPANHAR[area](id);
        return;
      }
      if (dados.encaminhado_hotelaria) renderEncaminhadoHotelaria(dados);
      else renderConfirmacao(dados);
    } catch (err) {
      if (err.dados && err.dados.acesso_expirado && window.HRGAcessoPaciente) {
        window.HRGAcessoPaciente.mostrarExpirado();
        return;
      }
      HRG.toast(err.message, "erro");
      enviandoChamado = false;
      if (botao) {
        botao.disabled = false;
        botao.textContent = "Enviar chamado";
      } else {
        renderOpcoes();
      }
      return;
    }
    enviandoChamado = false;
  }

  function barraPosEnvio(urlAcompanhar, rotulo) {
    el.barra.innerHTML = `
      <a class="botao botao-primario botao-bloco" href="${urlAcompanhar}">${rotulo}</a>
      <button type="button" class="botao secundario botao-bloco botao-inicio" id="botaoInicio">Voltar ao início</button>
    `;
    document.getElementById("botaoInicio").addEventListener("click", renderInicio);
  }

  function renderConfirmacao(chamado) {
    definirPasso(4, { marca: "Enfermagem" });
    el.tela.classList.add("tela-barra-dupla");
    el.tela.innerHTML = `
      <div class="cartao-passo texto-centro surgir">
        <div class="icone-confirmacao icone-sucesso">${ICONE_CHECK}</div>
        <h2>Chamado enviado!</h2>
        <p class="texto-suave">A equipe de enfermagem foi notificada.</p>
        <div class="resumo-linha"><span>Nº do chamado</span><b>#${chamado.id}</b></div>
        <div class="resumo-linha"><span>Leito</span><b>${escapeHtml(chamado.leito)}</b></div>
        <div class="resumo-linha"><span>Solicitação</span><b>${escapeHtml(chamado.subcategoria)}</b></div>
      </div>
    `;
    barraPosEnvio(URL_ACOMPANHAR.enfermagem(chamado.id), "Acompanhar chamado");
  }

  function renderEncaminhadoHotelaria(dados) {
    definirPasso(4, { marca: "Hotelaria" });
    el.tela.classList.add("tela-barra-dupla");
    el.tela.innerHTML = `
      <div class="cartao-passo texto-centro surgir">
        <div class="icone-confirmacao icone-hotelaria">${ICONE_ENCAMINHADO}</div>
        <h2>Pedido enviado!</h2>
        <p class="texto-suave">Sua solicitação foi enviada para a equipe de <b>${escapeHtml(dados.servico_nome)}</b>.</p>
        <div class="resumo-linha"><span>Leito</span><b>${escapeHtml(dados.leito)}</b></div>
        <div class="resumo-linha"><span>Serviço</span><b>${escapeHtml(dados.servico_nome)}</b></div>
      </div>
    `;
    barraPosEnvio(URL_ACOMPANHAR.hotelaria(dados.hotelaria_chamado_id), "Acompanhar solicitação");
  }

  // O leito sempre vem do QR Code afixado no quarto (validado no backend —
  // ver enfermagem/routes.py::paciente_inicio).
  const leito = window.LEITO_PREENCHIDO;
  state.andar = leito.andar;
  state.leito = leito.leito;
  renderInicio();
})();
