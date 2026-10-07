/* ==========================================================================
   HRG — utilitários compartilhados por Enfermagem e Hotelaria.

   Antes, cada uma das 9 páginas de JS reimplementava sua própria cópia de
   `escapeHtml`/`formatarMinutos`, cada `fetch` tratava erro de rede à sua
   maneira (ou nem tratava), e todo `alert()` interrompia a navegação com uma
   caixa de diálogo nativa. Este arquivo concentra essas peças, carregado
   antes do script de cada página (ver enfermagem/base.html e
   hotelaria/base.html) como um objeto global simples `window.HRG` — sem
   bundler, sem módulos ES, no mesmo espírito "script solto" do resto do
   projeto.
   ========================================================================== */
window.HRG = (function () {
  "use strict";

  function escapeHtml(texto) {
    const div = document.createElement("div");
    div.textContent = texto == null ? "" : String(texto);
    return div.innerHTML;
  }

  function formatarMinutos(min) {
    if (min == null || Number.isNaN(min)) return "—";
    const total = Math.round(min);
    if (total < 60) return `${total} min`;
    const horas = Math.floor(total / 60);
    const restante = total % 60;
    return `${horas}h ${String(restante).padStart(2, "0")}min`;
  }

  function formatarPercentual(valor) {
    if (valor == null || Number.isNaN(valor)) return "—";
    const sinal = valor > 0 ? "+" : "";
    return `${sinal}${valor}%`;
  }

  function debounce(fn, espera) {
    let temporizador = null;
    return function (...args) {
      clearTimeout(temporizador);
      temporizador = setTimeout(() => fn.apply(this, args), espera);
    };
  }

  // ------------------------------------------------------------------
  // Toast — substitui os `alert()` espalhados pelo código (bloqueiam a
  // tela inteira e são ruins em mobile). `tipo`: "erro" | "sucesso" | "info".
  // ------------------------------------------------------------------
  let containerToast = null;
  function containerDeToast() {
    if (!containerToast) {
      containerToast = document.createElement("div");
      containerToast.className = "hrg-toast-container";
      containerToast.setAttribute("role", "status");
      containerToast.setAttribute("aria-live", "polite");
      document.body.appendChild(containerToast);
    }
    return containerToast;
  }

  function toast(mensagem, tipo) {
    const container = containerDeToast();
    const item = document.createElement("div");
    item.className = `hrg-toast hrg-toast-${tipo || "info"}`;
    item.textContent = mensagem;
    container.appendChild(item);
    // Duplo rAF garante que a transição CSS de entrada realmente anime
    // (o navegador precisa "ver" o estado inicial antes de mudar a classe).
    requestAnimationFrame(() => requestAnimationFrame(() => item.classList.add("hrg-toast-visivel")));
    setTimeout(() => {
      item.classList.remove("hrg-toast-visivel");
      setTimeout(() => item.remove(), 300);
    }, 4500);
  }

  // ------------------------------------------------------------------
  // fetch com timeout e mensagem de erro sempre legível (nunca expõe
  // "Failed to fetch" ou stack técnico ao usuário final).
  // ------------------------------------------------------------------
  async function fetchJSON(url, opcoes) {
    opcoes = opcoes || {};
    const controlador = new AbortController();
    const sinalExterno = opcoes.signal;
    const tempoLimite = setTimeout(() => controlador.abort(), opcoes.timeout || 12000);
    if (sinalExterno) {
      if (sinalExterno.aborted) controlador.abort();
      else sinalExterno.addEventListener("abort", () => controlador.abort());
    }

    let resp;
    try {
      resp = await fetch(url, { ...opcoes, signal: controlador.signal });
    } catch (e) {
      clearTimeout(tempoLimite);
      if (e.name === "AbortError") {
        const erro = new Error("A solicitação demorou demais. Verifique sua conexão.");
        erro.abortado = true;
        throw erro;
      }
      const erro = new Error("Sem conexão com o servidor. Verifique sua internet e tente novamente.");
      erro.rede = true;
      throw erro;
    }
    clearTimeout(tempoLimite);

    let dados = null;
    try { dados = await resp.json(); } catch (e) { dados = null; }

    if (!resp.ok) {
      const erro = new Error((dados && dados.erro) || "Não foi possível completar a solicitação.");
      erro.status = resp.status;
      erro.dados = dados;
      throw erro;
    }
    return { dados, resposta: resp };
  }

  // ------------------------------------------------------------------
  // Polling "educado": pausa quando a aba não está visível (economiza
  // requisições em telas deixadas abertas por horas na Central/TV) e nunca
  // deixa duas execuções de `fn` rodarem sobrepostas.
  // ------------------------------------------------------------------
  function pollWhileVisible(fn, intervaloMs) {
    let executando = false;
    let ativo = true;

    async function tick() {
      if (!ativo || document.hidden || executando) return;
      executando = true;
      try {
        await fn();
      } finally {
        executando = false;
      }
    }

    function aoMudarVisibilidade() {
      if (!document.hidden) tick();
    }

    const idIntervalo = setInterval(tick, intervaloMs);
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    tick();

    return {
      parar() {
        ativo = false;
        clearInterval(idIntervalo);
        document.removeEventListener("visibilitychange", aoMudarVisibilidade);
      },
    };
  }

  // Detector simples de "os dados mudaram desde a última vez?" — usado para
  // pular um re-render (e evitar flicker/perda de scroll) quando o polling
  // trouxe exatamente o mesmo resultado de antes.
  function criarDetectorDeMudanca() {
    let ultimoHash = null;
    return function (dados) {
      const hash = JSON.stringify(dados);
      const houveMudanca = hash !== ultimoHash;
      ultimoHash = hash;
      return houveMudanca;
    };
  }

  // Fecha um modal/painel com a tecla Esc — `estaAberto()` decide se o
  // fechamento deve acontecer agora.
  function fecharComEsc(estaAberto, fechar) {
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && estaAberto()) fechar();
    });
  }

  // Trava simples contra duplo-clique/duplo-toque em botões de ação: chama
  // `fn` (que deve devolver uma Promise) e mantém o botão desabilitado
  // enquanto ela não resolve, restaurando o texto original ao final (mesmo
  // em caso de erro).
  async function comBotaoTravado(botao, fn) {
    if (!botao || botao.disabled) return;
    const textoOriginal = botao.textContent;
    botao.disabled = true;
    try {
      await fn();
    } finally {
      botao.disabled = false;
      if (botao.textContent !== textoOriginal) botao.textContent = textoOriginal;
    }
  }

  // ------------------------------------------------------------------
  // Alerta sonoro de novo chamado — usado nas telas de Central (painel
  // operacional). Toca um bipe curto via Web Audio API, sem depender de
  // nenhum arquivo de áudio. Navegadores só liberam som por script depois
  // de alguma interação do usuário na página; `prepararAudio()` (chamada
  // uma vez, abaixo) já deixa isso pronto a partir do primeiro clique/tecla
  // em qualquer tela, para o contexto de áudio já estar liberado quando o
  // primeiro chamado novo realmente chegar.
  // ------------------------------------------------------------------
  let contextoAudio = null;

  function obterContextoAudio() {
    if (!contextoAudio) {
      const Construtor = window.AudioContext || window.webkitAudioContext;
      if (!Construtor) return null;
      try { contextoAudio = new Construtor(); } catch (e) { return null; }
    }
    return contextoAudio;
  }

  function prepararAudio() {
    const desbloquear = () => {
      const ctx = obterContextoAudio();
      if (ctx && ctx.state === "suspended") ctx.resume();
    };
    document.addEventListener("click", desbloquear, { once: true });
    document.addEventListener("keydown", desbloquear, { once: true });
  }
  prepararAudio();

  function tocarAlertaNovoChamado() {
    try {
      const ctx = obterContextoAudio();
      if (!ctx) return;
      if (ctx.state === "suspended") ctx.resume();
      const agora = ctx.currentTime;
      // Dois bipes curtos — mais perceptível que um único tom, sem ser
      // uma sirene contínua.
      [0, 0.16].forEach((atraso) => {
        const osc = ctx.createOscillator();
        const ganho = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = 880;
        ganho.gain.setValueAtTime(0.0001, agora + atraso);
        ganho.gain.exponentialRampToValueAtTime(0.22, agora + atraso + 0.01);
        ganho.gain.exponentialRampToValueAtTime(0.0001, agora + atraso + 0.14);
        osc.connect(ganho);
        ganho.connect(ctx.destination);
        osc.start(agora + atraso);
        osc.stop(agora + atraso + 0.15);
      });
    } catch (e) {
      // Web Audio pode estar bloqueado (política do navegador/ambiente) —
      // nunca deve quebrar a tela por causa disso.
    }
  }

  // Detecta quais chamados de uma lista têm ID nunca visto antes — usado
  // para soar o alerta só quando um chamado realmente novo chega, nunca de
  // novo para o mesmo chamado. Na primeira chamada (tela recém-aberta), só
  // memoriza os IDs já existentes, sem soar alarme por eles.
  function criarDetectorDeNovosChamados() {
    let idsConhecidos = null;
    return function (chamados) {
      const idsAtuais = chamados.map((c) => c.id);
      if (idsConhecidos === null) {
        idsConhecidos = new Set(idsAtuais);
        return [];
      }
      const novos = chamados.filter((c) => !idsConhecidos.has(c.id));
      idsAtuais.forEach((id) => idsConhecidos.add(id));
      return novos;
    };
  }

  return {
    escapeHtml,
    formatarMinutos,
    formatarPercentual,
    debounce,
    toast,
    fetchJSON,
    pollWhileVisible,
    criarDetectorDeMudanca,
    fecharComEsc,
    comBotaoTravado,
    tocarAlertaNovoChamado,
    criarDetectorDeNovosChamados,
  };
})();
