(function () {
  "use strict";

  const ICONES = {
    urgencia: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    dor: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="16.4" cy="5" rx="2.7" ry="3.3" transform="rotate(15 16.4 5)"/><path d="M13.2 9.9c-2.6.1-4.4 1.6-5 4.1l-1.2 4.9c-.3 1.2.3 2.1 1.4 2.4l4.8 1.4"/><path d="M19.4 10.4c1 .8 1.6 2 1.6 3.3v4.6c0 1.4-1.1 2.5-2.5 2.5"/><path d="M18.6 19.8 11.9 13.4"/><path d="M11.9 16.2v2.3l3.2 1.7"/><path d="M4.6 9.8 3.4 11.6h2.2l-1.2 1.8"/><path d="M8.9 5.4 7.7 7.2h2.2l-1.2 1.8"/></svg>',
    soro: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.69s-5.5 6.24-5.5 10.19a5.5 5.5 0 0 0 11 0C17.5 8.93 12 2.69 12 2.69Z"/></svg>',
    falar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    outros: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 2-3 4"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
  };
  const ICONE_CHECK = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';

  // Ícones de serviço usados na subopção "Outros" — mesmo SVG já usado pela
  // Central de Hotelaria (ver static/js/hotelaria/central.js) para a tela
  // do paciente ficar visualmente consistente com quem vai atender.
  const ICONES_SERVICO = {
    bed: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4v16"/><path d="M2 8h18a2 2 0 0 1 2 2v10"/><path d="M2 17h20"/><path d="M6 8v9"/></svg>',
    utensils: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h2a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>',
    shirt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23Z"/></svg>',
    wrench: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94Z"/></svg>',
    limpeza: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 22-1-4"/><path d="M19 13.99a1 1 0 0 0 1-1V12a2 2 0 0 0-2-2h-3a1 1 0 0 1-1-1V4a2 2 0 0 0-4 0v5a1 1 0 0 1-1 1H6a2 2 0 0 0-2 2v.99a1 1 0 0 0 1 1"/><path d="M5 14h14l1.973 6.767A1 1 0 0 1 20 22H4a1 1 0 0 1-.973-1.233z"/><path d="m8 22 1-4"/></svg>',
  };

  // Emoji/ícone, dica curta e faixa de gravidade de cada subopção — dá às
  // demais categorias (Urgência, Soro, Falar com Enfermagem, Outros) o
  // mesmo desenho visual já usado pela escala de Dor (rosto/ícone colorido
  // + rótulo + dica), em vez da lista de texto simples. A faixa de
  // gravidade ("critica"/"media"/"baixa") segue os mesmos limiares do motor
  // de prioridade do backend (ver enfermagem/priority.py::_tier), então a
  // cor mostrada ao paciente nunca diverge da prioridade real do chamado.
  // "Outros" não tem gravidade (é encaminhado para a Hotelaria) — usa a cor
  // "hotelaria" e ícone de serviço em vez de emoji. "cor" (opcional)
  // sobrescreve só a cor do ícone, sem mudar a gravidade do chamado.
  const OPCOES_VISUAIS = {
    "Urgência": {
      "Não consigo respirar bem": { emoji: "😰", dica: "Dificuldade para respirar", grav: "critica" },
      "Sangramento intenso": { emoji: "🩸", dica: "Sangramento visível", grav: "critica" },
      "Queda ou acidente no quarto": { emoji: "🤕", dica: "Você caiu ou se machucou", grav: "critica" },
      "Confusão mental ou desmaio": { emoji: "😵", dica: "Perda de consciência ou confusão", grav: "critica" },
      "Dor súbita e muito intensa": { emoji: "😖", dica: "Dor forte que começou de repente", grav: "critica" },
      "Outra emergência": { emoji: "🚨", dica: "Qualquer outra situação grave", grav: "critica" },
    },
    "Soro": {
      "Está retornando sangue": { emoji: "🩸", dica: "Sangue voltando pelo equipo — avise a equipe", grav: "media", cor: "vermelho" },
      "Problema no acesso": { emoji: "⚠️", dica: "Acesso solto, dolorido ou vazando", grav: "media", cor: "laranja" },
      "Acabou": { emoji: "💧", dica: "O soro do frasco já terminou", grav: "media", cor: "verde" },
      "Outro problema": { emoji: "❓", dica: "Qualquer outra dificuldade com o soro", grav: "media" },
      "Está perto do fim": { emoji: "⏳", dica: "Ainda dá tempo, mas já avise a equipe", grav: "baixa", cor: "verde" },
    },
    "Falar com Enfermagem": {
      "Dúvida sobre medicação": { emoji: "💊", dica: "Perguntas sobre remédios", grav: "baixa" },
      "Dúvida sobre procedimento ou alta": { emoji: "📋", dica: "Perguntas sobre exames, alta ou rotina", grav: "baixa" },
      "Preciso de orientação": { emoji: "🧭", dica: "Qualquer orientação da equipe", grav: "baixa" },
      "Assunto geral": { emoji: "💬", dica: "Outro assunto não urgente", grav: "baixa" },
    },
    "Outros": {
      "Acomodação (cama, travesseiro, TV, ar-condicionado)": { icone: "bed", dica: "Poltrona, colchão, TV ou ar-condicionado", grav: "hotelaria" },
      "Alimentação": { icone: "utensils", dica: "Refeição, lanche ou dieta especial", grav: "hotelaria" },
      "Roupa de cama / Enxoval": { icone: "shirt", dica: "Lençol, travesseiro ou toalhas", grav: "hotelaria" },
      "Manutenção do quarto": { icone: "wrench", dica: "Chuveiro, luz ou parte elétrica/hidráulica", grav: "hotelaria" },
      "Limpeza do quarto ou banheiro": { icone: "limpeza", dica: "Limpeza ou higienização do quarto", grav: "hotelaria" },
    },
  };

  // Escala de dor: 4 níveis, do mais grave para o mais leve (mesma ordem
  // da lista em enfermagem/constants.py::CATEGORIAS["Dor"]["opcoes"]).
  // Cada nível vira um botão gigante com rosto + cor, para que o paciente
  // possa escolher pela expressão facial mesmo sem conseguir ler.
  const NIVEIS_DOR = [
    { rosto: "🥵", nivel: 4, curto: "Dor no peito",   dica: "Aperto no peito ou falta de ar — chamamos AGORA" },
    { rosto: "😖", nivel: 3, curto: "Dor muito forte", dica: "Difícil de aguentar" },
    { rosto: "😣", nivel: 2, curto: "Dor moderada",    dica: "Incomoda, mas dá pra aguentar" },
    { rosto: "🙂", nivel: 1, curto: "Dor leve",        dica: "Pequena, quase não atrapalha" },
  ];
  const ICONE_ENCAMINHADO = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>';

  const CATEGORIAS_ORDEM = Object.keys(window.CATEGORIAS || {});
  // "Falar com Enfermagem" é a única categoria sem passo de confirmação: o
  // chamado é criado assim que o paciente escolhe a subopção — pedido
  // explícito do hospital para agilizar solicitações simples (dúvidas,
  // orientação) que não são urgentes. Todas as demais categorias passam
  // pelo passo 4 (confirmação) antes do envio.
  const CATEGORIA_ENVIO_DIRETO = "Falar com Enfermagem";
  // Mesma ideia já usada pela Hotelaria: guardamos apenas a REFERÊNCIA
  // (id + leito) do chamado ativo neste dispositivo. O conteúdo do chamado
  // em si nunca é lido daqui — sempre vem do banco de dados via API. Isso
  // existe só para que um F5 / fechar-e-reabrir o navegador não faça o
  // paciente "perder" o chamado que acabou de enviar antes de clicar em
  // "Acompanhar chamado".
  const LS_ATIVO = "rg_enfermagem_chamado_ativo";
  // Mesma ideia para pedidos de Hotelaria feitos por "Outros" (chave já
  // usada antes pela tela /hotelaria/paciente, mantida para não perder o
  // acompanhamento de quem já tinha um pedido aberto).
  const LS_ATIVO_HOTELARIA = "rg_hospital_chamado_ativo";

  const el = {
    tela: document.getElementById("telaPaciente"),
    barra: document.getElementById("barraInferior"),
    botaoVoltar: document.getElementById("botaoVoltar"),
    trilha: document.querySelectorAll("#trilhaPassos span"),
  };

  const state = {
    passo: 1,
    andar: "",
    leito: "",
    categoria: "",
    subcategoria: "",
  };

  const escapeHtml = HRG.escapeHtml;

  // Nome do andar para exibição, sem o sufixo "— LEITOS" (o valor original
  // continua sendo usado como chave/valor real do <select> e do chamado).
  function labelAndar(andar) {
    return (andar || "").replace(/\s*—\s*LEITOS\s*$/i, "");
  }

  function definirPasso(numero) {
    state.passo = numero;
    el.trilha.forEach((span) => {
      span.classList.toggle("ativo", parseInt(span.dataset.passo, 10) <= numero);
    });
    el.botaoVoltar.style.visibility = numero <= 2 ? "hidden" : "visible";
    // Passo 2 não usa a barra inferior (a escolha já avança de tela) — sem
    // essa classe, o espaço reservado para a barra sobraria embaixo e
    // empurraria as 5 categorias para fora da tela em telas menores.
    el.tela.classList.toggle("tela-sem-barra", numero === 2);
  }

  // -------------------------------------------------------------------
  // Passo 2: "Como podemos ajudar?"
  // -------------------------------------------------------------------
  function renderPasso2() {
    definirPasso(2);
    const botoes = CATEGORIAS_ORDEM.map((nome) => {
      const dados = window.CATEGORIAS[nome];
      // Só "Outros" mantém a descrição: as demais categorias têm nomes
      // autoexplicativos e ganham mais espaço em tela sem o texto extra.
      const mostrarDescricao = nome === "Outros" && dados.descricao;
      return `
        <button type="button" class="cartao-categoria cor-${dados.cor}" data-categoria="${escapeHtml(nome)}">
          <span class="icone-categoria">${ICONES[dados.icone] || ""}</span>
          <span class="texto-categoria">
            <strong>${escapeHtml(nome)}</strong>
            ${mostrarDescricao ? `<small title="${escapeHtml(dados.descricao)}">${escapeHtml(dados.descricao)}</small>` : ""}
          </span>
        </button>
      `;
    }).join("");

    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>Como podemos ajudar?</h1>
        <p>Leito ${escapeHtml(state.leito)} · ${escapeHtml(labelAndar(state.andar))}</p>
      </div>
      <div class="grade-categorias surgir">${botoes}</div>
    `;
    el.barra.innerHTML = "";
    el.botaoVoltar.style.visibility = "hidden";

    el.tela.querySelectorAll(".cartao-categoria").forEach((botao) => {
      botao.addEventListener("click", () => {
        state.categoria = botao.dataset.categoria;
        state.subcategoria = "";
        renderPasso3();
      });
    });
  }

  // -------------------------------------------------------------------
  // Passo 3: subopções
  // -------------------------------------------------------------------
  function renderPasso3() {
    definirPasso(3);
    const dados = window.CATEGORIAS[state.categoria];
    const envioDireto = state.categoria === CATEGORIA_ENVIO_DIRETO;
    const eDor = state.categoria === "Dor";
    state.subcategoria = "";

    let listaHtml;
    if (eDor) {
      // Escala visual de dor (rosto + cor + rótulo). Cada opção é mapeada
      // para a subopção equivalente já cadastrada em CATEGORIAS.Dor.opcoes
      // (busca por prefixo/nome curto), preservando o peso de gravidade que
      // o backend usa para priorizar.
      const opcoesDisponiveis = dados.opcoes; // apenas strings
      const encontraOpcao = (curto) => opcoesDisponiveis.find((o) => o === curto) ||
                                        opcoesDisponiveis.find((o) => o.toLowerCase().startsWith(curto.toLowerCase().split(" ")[0]));
      listaHtml = `<div class="escala-dor surgir">` + NIVEIS_DOR
        .filter((n) => encontraOpcao(n.curto))
        .map((n) => {
          const opcao = encontraOpcao(n.curto);
          return `
            <button type="button" class="opcao-dor nivel-${n.nivel}" data-opcao="${escapeHtml(opcao)}">
              <span class="rosto-dor" aria-hidden="true">${n.rosto}</span>
              <span class="texto-dor">
                <strong>${escapeHtml(n.curto)}</strong>
                <small>${escapeHtml(n.dica)}</small>
              </span>
            </button>
          `;
        }).join("") + `</div>`;
    } else if (OPCOES_VISUAIS[state.categoria]) {
      // Mesmo desenho visual da escala de Dor (ícone colorido + rótulo +
      // dica) para as demais categorias, em vez da lista de texto simples.
      const visuais = OPCOES_VISUAIS[state.categoria];
      listaHtml = `<div class="escala-dor surgir">` + dados.opcoes.map((texto) => {
        const v = visuais[texto] || {};
        const simbolo = v.icone ? (ICONES_SERVICO[v.icone] || "") : (v.emoji || "•");
        return `
          <button type="button" class="opcao-dor grav-${v.grav || "media"}${v.cor ? ` cor-${v.cor}` : ""}" data-opcao="${escapeHtml(texto)}">
            <span class="rosto-dor" aria-hidden="true">${simbolo}</span>
            <span class="texto-dor">
              <strong>${escapeHtml(texto)}</strong>
              ${v.dica ? `<small>${escapeHtml(v.dica)}</small>` : ""}
            </span>
          </button>
        `;
      }).join("") + `</div>`;
    } else {
      // Reserva: categoria futura sem mapa visual em OPCOES_VISUAIS ainda.
      listaHtml = `<div class="lista-subcategorias surgir">` + dados.opcoes.map((texto) => `
        <button type="button" class="opcao-subcategoria" data-opcao="${escapeHtml(texto)}">
          <span>${escapeHtml(texto)}</span>
          <span class="marcador-opcao"></span>
        </button>
      `).join("") + `</div>`;
    }

    const usaEscalaVisual = eDor || Boolean(OPCOES_VISUAIS[state.categoria]);

    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>${escapeHtml(state.categoria)}</h1>
        <p>${eDor ? "Toque no rosto que mostra como você está" : (envioDireto ? "Escolha o assunto e toque em Selecionar — o chamado é enviado na hora" : "Escolha a opção que melhor descreve a situação")}</p>
      </div>
      ${listaHtml}
    `;
    el.botaoVoltar.onclick = renderPasso2;

    const seletor = usaEscalaVisual ? ".opcao-dor" : ".opcao-subcategoria";

    if (envioDireto) {
      // Sem passo de confirmação: o paciente marca o assunto e toca em
      // "Selecionar" — o chamado é criado nesse momento (evita envio
      // acidental com um toque só, mas continua sem a tela de resumo).
      el.barra.innerHTML = `<button class="botao botao-primario botao-bloco" id="botaoSelecionar" disabled>Selecionar</button>`;
      const botaoSelecionar = document.getElementById("botaoSelecionar");
      el.tela.querySelectorAll(seletor).forEach((botao) => {
        botao.addEventListener("click", () => {
          el.tela.querySelectorAll(seletor).forEach((b) => b.classList.remove("selecionada"));
          botao.classList.add("selecionada");
          state.subcategoria = botao.dataset.opcao;
          botaoSelecionar.disabled = false;
        });
      });
      botaoSelecionar.addEventListener("click", () => {
        if (!state.subcategoria) return;
        botaoSelecionar.disabled = true;
        botaoSelecionar.textContent = "Enviando...";
        el.tela.querySelectorAll(seletor).forEach((b) => { b.disabled = true; });
        enviarChamado();
      });
      return;
    }

    el.barra.innerHTML = `<button class="botao botao-primario botao-bloco" id="botaoContinuar3" disabled>Continuar</button>`;
    const botaoContinuar = document.getElementById("botaoContinuar3");
    el.tela.querySelectorAll(seletor).forEach((botao) => {
      botao.addEventListener("click", () => {
        el.tela.querySelectorAll(seletor).forEach((b) => b.classList.remove("selecionada"));
        botao.classList.add("selecionada");
        state.subcategoria = botao.dataset.opcao;
        botaoContinuar.disabled = false;
      });
    });

    botaoContinuar.addEventListener("click", renderPasso4);
  }

  // -------------------------------------------------------------------
  // Passo 4: resumo + envio
  // -------------------------------------------------------------------
  function renderPasso4() {
    definirPasso(4);
    el.tela.innerHTML = `
      <div class="cabecalho-passo">
        <h1>Confirme seu chamado</h1>
        <p>Revise as informações antes de enviar</p>
      </div>
      <div class="cartao-passo surgir">
        <div class="resumo-linha"><span>Leito</span><b>${escapeHtml(state.leito)}</b></div>
        <div class="resumo-linha"><span>Andar</span><b>${escapeHtml(labelAndar(state.andar))}</b></div>
        <div class="resumo-linha"><span>Motivo</span><b>${escapeHtml(state.categoria)}</b></div>
        <div class="resumo-linha"><span>Solicitação</span><b>${escapeHtml(state.subcategoria)}</b></div>
      </div>
    `;
    el.barra.innerHTML = `<button class="botao botao-primario botao-bloco" id="botaoEnviar">Enviar chamado</button>`;
    el.botaoVoltar.onclick = renderPasso3;

    document.getElementById("botaoEnviar").addEventListener("click", enviarChamado);
  }

  // Trava contra duplo-envio mesmo que o usuário consiga clicar duas vezes
  // muito rápido (o backend também protege contra isso — ver
  // enfermagem/api.py — mas evitar a segunda requisição já no cliente
  // poupa uma viagem de rede desnecessária).
  let enviandoChamado = false;

  async function enviarChamado() {
    if (enviandoChamado) return;
    enviandoChamado = true;

    // Existe apenas no fluxo com passo de confirmação (passo 4); no envio
    // direto de "Falar com Enfermagem" o botão "Selecionar" do passo 3 já
    // foi travado antes de chamar esta função.
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

      if (dados.encaminhado_hotelaria) {
        renderEncaminhadoHotelaria(dados);
      } else {
        try { localStorage.setItem(LS_ATIVO, JSON.stringify({ id: dados.id, leito: dados.leito })); } catch (e) {}
        renderConfirmacao(dados);
      }
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
        // Envio direto (sem passo de confirmação): reabre o passo 3 para
        // que o paciente possa tentar novamente.
        renderPasso3();
      }
      return;
    }
    enviandoChamado = false;
  }

  // -------------------------------------------------------------------
  // Confirmação: chamado de enfermagem enviado
  // -------------------------------------------------------------------
  function renderConfirmacao(chamado) {
    definirPasso(4);
    el.botaoVoltar.style.visibility = "hidden";
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
    el.barra.innerHTML = `<a class="botao botao-primario botao-bloco" href="/enfermagem/acompanhar/${chamado.id}">Acompanhar chamado</a>`;
  }

  // -------------------------------------------------------------------
  // Confirmação: encaminhado para a Central de Hotelaria
  // -------------------------------------------------------------------
  function renderEncaminhadoHotelaria(dados) {
    definirPasso(4);
    el.botaoVoltar.style.visibility = "hidden";
    el.tela.innerHTML = `
      <div class="cartao-passo texto-centro surgir">
        <div class="icone-confirmacao icone-hotelaria">${ICONE_ENCAMINHADO}</div>
        <h2>Encaminhado para a Hotelaria!</h2>
        <p class="texto-suave">Sua solicitação foi enviada para a equipe de <b>${escapeHtml(dados.servico_nome)}</b>.</p>
        <div class="resumo-linha"><span>Leito</span><b>${escapeHtml(dados.leito)}</b></div>
        <div class="resumo-linha"><span>Serviço</span><b>${escapeHtml(dados.servico_nome)}</b></div>
      </div>
    `;
    // Grava apenas a REFERÊNCIA do chamado (id + leito) no localStorage deste
    // dispositivo — o conteúdo do chamado em si sempre vem do banco de
    // dados. `iniciar()` usa isso para retomar o acompanhamento depois de um
    // F5 / fechar-e-reabrir o navegador.
    try {
      localStorage.setItem(LS_ATIVO_HOTELARIA, JSON.stringify({ id: dados.hotelaria_chamado_id, leito: dados.leito }));
    } catch (e) {}

    el.barra.innerHTML = `<a class="botao botao-primario botao-bloco" href="/enfermagem/acompanhar-hotelaria/${dados.hotelaria_chamado_id}">Acompanhar solicitação</a>`;
  }

  // -------------------------------------------------------------------
  // Inicialização: retomar chamado ativo (se houver) antes de começar um
  // novo. Evita que uma atualização de página (F5) ou o fechamento
  // acidental da aba antes de clicar em "Acompanhar chamado" faça o
  // paciente perder de vista um chamado que já foi enviado.
  // -------------------------------------------------------------------
  async function iniciar() {
    let salvo = null;
    try { salvo = JSON.parse(localStorage.getItem(LS_ATIVO) || "null"); } catch (e) {}

    if (salvo && salvo.id) {
      try {
        const resp = await fetch(`/api/enfermagem/chamados/${salvo.id}`);
        if (resp.ok) {
          const chamado = await resp.json();
          if (chamado.status !== "finalizado") {
            // Chamado ainda em andamento: leva o paciente direto para o
            // acompanhamento em vez de reiniciar o fluxo do zero.
            window.location.href = `/enfermagem/acompanhar/${chamado.id}`;
            return;
          }
        }
      } catch (e) {}
      // Chamado já finalizado (ou não encontrado/erro de rede): libera o
      // dispositivo para um novo chamado — a avaliação, quando aplicável,
      // já foi oferecida na própria tela de acompanhamento enquanto o
      // chamado estava ativo, e é sempre opcional.
      try { localStorage.removeItem(LS_ATIVO); } catch (e) {}
    }

    // Pedido de Hotelaria em aberto neste dispositivo (ou já finalizado, mas
    // ainda sem avaliação): leva direto ao acompanhamento.
    let salvoHotelaria = null;
    try { salvoHotelaria = JSON.parse(localStorage.getItem(LS_ATIVO_HOTELARIA) || "null"); } catch (e) {}
    if (salvoHotelaria && salvoHotelaria.id) {
      try {
        const resp = await fetch(`/hotelaria/api/chamados/${salvoHotelaria.id}`);
        if (resp.ok) {
          const chamado = await resp.json();
          if (chamado.status !== "finalizado" || !chamado.tem_avaliacao) {
            window.location.href = `/enfermagem/acompanhar-hotelaria/${chamado.id}`;
            return;
          }
        }
      } catch (e) {}
      try { localStorage.removeItem(LS_ATIVO_HOTELARIA); } catch (e) {}
    }

    // O leito sempre vem do QR Code afixado no quarto (validado e
    // com leito ativo no backend — ver enfermagem/routes.py::paciente_inicio).
    const leito = window.LEITO_PREENCHIDO;
    state.andar = leito.andar;
    state.leito = leito.leito;
    renderPasso2();
  }

  iniciar();
})();
