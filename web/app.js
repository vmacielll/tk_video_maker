// Gerador de Vídeos — lógica do frontend
(function () {
  "use strict";

  var imagemInput = document.getElementById("imagem");
  var dropzone = document.getElementById("dropzone");
  var dropzoneTexto = document.getElementById("dropzone-texto");
  var preview = document.getElementById("preview");
  var textos = document.getElementById("textos");
  var duracao = document.getElementById("duracao");
  var fade = document.getElementById("fade");
  var fonte = document.getElementById("fonte");
  var cor = document.getElementById("cor");
  var corDestaque = document.getElementById("cor-destaque");
  var escurecer = document.getElementById("escurecer");
  var escurecerValor = document.getElementById("escurecer-valor");
  var tamanho = document.getElementById("tamanho");
  var tamanhoValor = document.getElementById("tamanho-valor");
  var cartaoPreview = document.getElementById("cartao-preview");
  var previewFrameBg = document.getElementById("preview-frame-bg");
  var previewFrameOverlay = document.getElementById("preview-frame-overlay");
  var temaAuto = document.getElementById("tema-auto");
  var gerarAutoBtn = document.getElementById("gerar-auto");
  var autoStatus = document.getElementById("auto-status");
  var resultadoLegenda = document.getElementById("resultado-legenda");
  var legendaTexto = document.getElementById("legenda-texto");
  var copiarLegendaBtn = document.getElementById("copiar-legenda");
  var fundoGrid = document.getElementById("fundo-grid");
  var buscarMaisBtn = document.getElementById("buscar-mais");
  var gerarFrasesBtn = document.getElementById("gerar-frases");
  var gerarLegendaBtn = document.getElementById("gerar-legenda");
  var buscaImagem = document.getElementById("busca-imagem");
  var temaBuscaMap = {};
  var ctaSelect = document.getElementById("cta");
  var temaCtaMap = {};
  var buscarImagensBtn = document.getElementById("buscar-imagens");
  var templatesEl = document.getElementById("templates");
  var gerarBtn = document.getElementById("gerar");
  var alerta = document.getElementById("alerta");
  var resultado = document.getElementById("resultado");
  var videoResultado = document.getElementById("video-resultado");
  var linkDownload = document.getElementById("link-download");
  var listaVideos = document.getElementById("lista-videos");

  var imagemBase64 = null;
  var imagensLista = null;
  var temaAtual = "";
  var pagina = 1;

  // Layout do texto (template): "" = automático (o servidor sorteia a cada vídeo)
  var templateAtual = "";
  var COR_DESTAQUE_PADRAO = "#d4af37";
  var corDestaqueAtual = COR_DESTAQUE_PADRAO;

  // Slider de escurecimento
  escurecer.addEventListener("input", function () {
    escurecerValor.textContent = escurecer.value;
    agendarPreview();
  });

  // Slider de tamanho do texto
  tamanho.addEventListener("input", function () {
    tamanhoValor.textContent = tamanho.value;
    agendarPreview();
  });

  // Re-dispara o preview quando texto/opções mudam
  textos.addEventListener("input", agendarPreview);
  fonte.addEventListener("change", agendarPreview);
  cor.addEventListener("input", agendarPreview);
  corDestaque.addEventListener("input", function () {
    corDestaqueAtual = corDestaque.value;
    agendarPreview();
  });

  // Seletor de layout (chips de template)
  function wireChips() {
    Array.prototype.forEach.call(templatesEl.querySelectorAll(".chip"), function (chip) {
      chip.addEventListener("click", function () {
        selecionarTemplate(chip.dataset.template);
        agendarPreview();
      });
    });
  }

  function renderTemplates(lista) {
    templatesEl.innerHTML = "";
    var auto = document.createElement("button");
    auto.type = "button";
    auto.className = "chip chip-auto";
    auto.dataset.template = "";
    auto.textContent = "Automático";
    templatesEl.appendChild(auto);
    (lista || []).forEach(function (t) {
      var chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.dataset.template = t.id;
      chip.textContent = t.nome;
      templatesEl.appendChild(chip);
    });
    wireChips();
    selecionarTemplate(templateAtual);
  }

  function selecionarTemplate(id) {
    templateAtual = id || "";
    var chips = Array.prototype.slice.call(templatesEl.querySelectorAll(".chip"));
    if (!chips.length) { return; }
    var alvo = null;
    chips.forEach(function (chip) {
      if (chip.dataset.template === templateAtual) { alvo = chip; }
    });
    if (!alvo) {
      // id desconhecido pelo seletor: volta para "Automático"
      templateAtual = "";
      alvo = chips[0];
    }
    chips.forEach(function (chip) {
      var ativo = chip === alvo;
      chip.classList.toggle("chip-ativo", ativo);
      chip.setAttribute("aria-pressed", ativo ? "true" : "false");
    });
  }

  function carregarTemplates() {
    fetch("/api/templates")
      .then(function (r) {
        if (!r.ok) { throw new Error("erro"); }
        return r.json();
      })
      .then(function (dados) {
        if (dados.templates && dados.templates.length) {
          renderTemplates(dados.templates);
        }
      })
      .catch(function () {
        /* sem /api/templates ainda: mantém os chips do HTML */
      });
  }

  wireChips();
  carregarTemplates();

  // Upload por clique
  dropzone.addEventListener("click", function () {
    imagemInput.click();
  });

  // Drag & drop
  ["dragover", "dragenter"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag");
    });
  });
  dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer.files.length) {
      definirImagem(e.dataTransfer.files[0]);
    }
  });

  imagemInput.addEventListener("change", function () {
    if (imagemInput.files.length) {
      definirImagem(imagemInput.files[0]);
    }
  });

  function definirImagem(arquivo) {
    var leitor = new FileReader();
    leitor.onload = function () {
      imagensLista = null;
      temaAtual = "";
      // imagem manual, sem tema: volta pra cor de destaque padrão (dourada)
      corDestaqueAtual = COR_DESTAQUE_PADRAO;
      corDestaque.value = COR_DESTAQUE_PADRAO;
      imagemBase64 = leitor.result;
      preview.src = leitor.result;
      preview.hidden = false;
      dropzoneTexto.textContent = "Imagem carregada — clique para trocar";
      renderFundoGrid();
      agendarPreview();
    };
    leitor.readAsDataURL(arquivo);
  }

  // Geração
  gerarBtn.addEventListener("click", function () {
    if (!imagemBase64) {
      mostrarAlerta("Escolha uma imagem de fundo primeiro.");
      return;
    }
    if (!textos.value.trim()) {
      mostrarAlerta("Escreva pelo menos uma frase.");
      return;
    }

    gerarBtn.disabled = true;
    gerarBtn.textContent = "Gerando…";
    esconderAlerta();

    var payload = {
      textos: textos.value,
      duracao: parseFloat(duracao.value) || 2.5,
      fade: parseFloat(fade.value) || 0.4,
      fonte: fonte.value,
      cor: cor.value,
      escurecer: parseInt(escurecer.value) || 0,
      tamanho: parseInt(tamanho.value) || 100,
      template: templateAtual,
      cor_destaque: corDestaqueAtual
    };
    if (imagensLista && imagensLista.length) {
      payload.imagens = imagensLista;
    } else {
      payload.imagem = imagemBase64;
    }

    fetch("/api/gerar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (resp) {
        return resp.json().then(function (dados) {
          return { status: resp.status, dados: dados };
        });
      })
      .then(function (res) {
        if (!res.dados.ok) {
          mostrarAlerta(res.dados.erro || "Erro ao gerar o vídeo.");
          return;
        }
        resultado.hidden = false;
        videoResultado.src = res.dados.url;
        linkDownload.href = res.dados.url;
        linkDownload.setAttribute("download", res.dados.nome);
        resultado.scrollIntoView({ behavior: "smooth" });
        carregarVideos();
      })
      .catch(function () {
        mostrarAlerta("Não foi possível conectar ao servidor. Verifique se ele está rodando.");
      })
      .finally(function () {
        gerarBtn.disabled = false;
        gerarBtn.textContent = "Gerar vídeo";
      });
  });

  function mostrarAlerta(msg) {
    alerta.textContent = msg;
    alerta.hidden = false;
    alerta.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function esconderAlerta() {
    alerta.hidden = true;
  }

  // Pré-visualização do texto
  var previewTimer = null;

  function agendarPreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(atualizarPreview, 350);
  }

  function atualizarPreview() {
    if (!imagemBase64) {
      cartaoPreview.hidden = true;
      return;
    }
    var primeiraFrase = (textos.value || "").trim().split("\n")[0] || "";
    if (!primeiraFrase) {
      cartaoPreview.hidden = true;
      return;
    }
    var payload = {
      imagem: imagemBase64,
      texto: primeiraFrase,
      fonte: fonte.value,
      cor: cor.value,
      escurecer: parseInt(escurecer.value) || 0,
      tamanho: parseInt(tamanho.value) || 100,
      template: templateAtual,
      cor_destaque: corDestaqueAtual
    };
    fetch("/api/preview_camadas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
      .then(function (resp) {
        if (!resp.ok) { throw new Error("erro"); }
        return resp.json();
      })
      .then(function (data) {
        if (!data.ok) { throw new Error(data.erro || "erro"); }
        // bg: animado pelo CSS (kenburns). overlay: estático por cima.
        if (previewFrameBg._url) { URL.revokeObjectURL(previewFrameBg._url); }
        if (previewFrameOverlay._url) { URL.revokeObjectURL(previewFrameOverlay._url); }
        var bgUrl = "data:image/png;base64," + data.bg;
        var ovUrl = "data:image/png;base64," + data.overlay;
        previewFrameBg._url = bgUrl;
        previewFrameOverlay._url = ovUrl;
        previewFrameBg.src = bgUrl;
        previewFrameOverlay.src = ovUrl;
        cartaoPreview.hidden = false;
      })
      .catch(function () {
        /* silencioso */
      });
  }

  // Lista de vídeos
  function carregarVideos() {
    fetch("/api/videos")
      .then(function (resp) {
        return resp.json();
      })
      .then(function (dados) {
        listaVideos.innerHTML = "";
        if (!dados.videos || !dados.videos.length) {
          listaVideos.innerHTML = '<p class="vazio">Nenhum vídeo gerado ainda.</p>';
          return;
        }
        dados.videos.forEach(function (v) {
          var item = document.createElement("div");
          item.className = "item-video";

          var video = document.createElement("video");
          video.src = v.url;
          video.controls = true;
          video.preload = "metadata";

          var link = document.createElement("a");
          link.href = v.url;
          link.setAttribute("download", v.nome);
          link.textContent = "Baixar";
          link.className = "botao-download";

          item.appendChild(video);
          item.appendChild(link);
          listaVideos.appendChild(item);
        });
      })
      .catch(function () {
        /* silencioso */
      });
  }

  // Modo automático (tema -> fundo Pexels + texto -> vídeo)
  function carregarTemas() {
    fetch("/api/temas")
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        temaAuto.innerHTML = "";
        temaBuscaMap = {};
        temaCtaMap = {};
        (dados.temas || []).forEach(function (t) {
          var nome = t.nome || t;
          var busca = t.busca || "";
          var cta = (t.cta || "").trim();
          temaBuscaMap[nome] = busca;
          temaCtaMap[nome] = cta;
          var opt = document.createElement("option");
          opt.value = nome;
          opt.textContent = nome;
          temaAuto.appendChild(opt);
        });
        // lista de CTAs salvos (sem repetir, na ordem em que aparecem)
        var ctasVistos = {};
        var ctasOrdem = [];
        (dados.temas || []).forEach(function (t) {
          var c = (t.cta || "").trim();
          if (c && !ctasVistos[c]) {
            ctasVistos[c] = true;
            ctasOrdem.push(c);
          }
        });
        ctaSelect.innerHTML = "";
        var padrao = document.createElement("option");
        padrao.value = "";
        padrao.textContent = "Padrão do tema";
        ctaSelect.appendChild(padrao);
        ctasOrdem.forEach(function (c) {
          var o = document.createElement("option");
          o.value = c;
          o.textContent = c;
          ctaSelect.appendChild(o);
        });
        if (!temaAuto.options.length) {
          temaAuto.innerHTML = '<option value="">Nenhum tema</option>';
        } else {
          atualizarBuscaImagem();
          atualizarCta();
        }
      })
      .catch(function () {
        temaAuto.innerHTML = '<option value="">Erro ao carregar temas</option>';
      });
  }

  function atualizarBuscaImagem() {
    var nome = temaAuto.value;
    buscaImagem.value = temaBuscaMap[nome] || "";
  }

  function atualizarCta() {
    var ctaTema = temaCtaMap[temaAuto.value] || "";
    var opcoes = Array.prototype.slice.call(ctaSelect.options);
    var existe = opcoes.some(function (o) { return o.value === ctaTema; });
    // seleciona o CTA do tema; se não estiver na lista, fica "Padrão do tema"
    ctaSelect.value = existe ? ctaTema : "";
  }

  temaAuto.addEventListener("change", function () {
    atualizarBuscaImagem();
    atualizarCta();
  });

  gerarAutoBtn.addEventListener("click", function () {
    var tema = temaAuto.value;
    if (!tema) {
      mostrarAlerta("Escolha um tema.");
      return;
    }
    gerarAutoBtn.disabled = true;
    gerarAutoBtn.textContent = "Preparando…";
    autoStatus.hidden = false;
    autoStatus.textContent = "Buscando fundo e texto…";
    esconderAlerta();

    fetch("/api/preparar_auto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tema: tema, busca: buscaImagem.value, cta: ctaSelect.value })
    })
      .then(function (resp) {
        return resp.json().then(function (d) { return { status: resp.status, dados: d }; });
      })
      .then(function (res) {
        if (!res.dados.ok) {
          mostrarAlerta(res.dados.erro || "Erro ao preparar.");
          autoStatus.hidden = true;
          return;
        }
        // preenche o formulário para você revisar antes de aprovar
        imagensLista = res.dados.imagens || [];
        temaAtual = tema;
        pagina = 1;
        if (res.dados.cor) {
          corDestaqueAtual = res.dados.cor;
          corDestaque.value = res.dados.cor;
        }
        if (res.dados.template) {
          // mostra pro usuário qual layout foi sorteado (ele pode trocar)
          selecionarTemplate(res.dados.template);
        }
        if (!ctaSelect.value) {
          // veio "Padrão do tema": mostra qual CTA o tema usa de fato
          atualizarCta();
        }
        if (imagensLista.length) {
          atualizarImagemBase64();
          dropzoneTexto.textContent = imagensLista.length + " fundos carregados (um por linha) — remova os que não gostar";
        }
        textos.value = (res.dados.frases || []).join("\n");
        legendaTexto.value = res.dados.legenda || "";
        resultadoLegenda.hidden = false;
        renderFundoGrid();
        agendarPreview();
        autoStatus.textContent = "Pronto! Revise os fundos e o texto, depois clique em 'Gerar vídeo'.";
        textos.scrollIntoView({ behavior: "smooth", block: "center" });
      })
      .catch(function () {
        mostrarAlerta("Não foi possível conectar ao servidor.");
        autoStatus.hidden = true;
      })
      .finally(function () {
        gerarAutoBtn.disabled = false;
        gerarAutoBtn.textContent = "Preencher com tema";
      });
  });

  copiarLegendaBtn.addEventListener("click", function () {
    legendaTexto.select();
    document.execCommand("copy");
    copiarLegendaBtn.textContent = "Copiado!";
    setTimeout(function () { copiarLegendaBtn.textContent = "Copiar legenda"; }, 2000);
  });

  // Grade de fundos: remover + buscar mais
  function targetCount() {
    var linhas = (textos.value || "").split("\n").filter(function (l) { return l.trim(); });
    return linhas.length || 1;
  }

  function atualizarImagemBase64() {
    if (imagensLista && imagensLista.length) {
      imagemBase64 = imagensLista[0];
      preview.src = imagensLista[0];
      preview.hidden = false;
    }
  }

  function renderFundoGrid() {
    fundoGrid.innerHTML = "";
    if (!imagensLista || !imagensLista.length) {
      fundoGrid.hidden = true;
      buscarMaisBtn.hidden = true;
      return;
    }
    fundoGrid.hidden = false;
    imagensLista.forEach(function (url, i) {
      var item = document.createElement("div");
      item.className = "fundo-item";
      var img = document.createElement("img");
      img.src = url;
      img.alt = "Fundo " + (i + 1);
      var btn = document.createElement("button");
      btn.className = "fundo-remover";
      btn.textContent = "×";
      btn.title = "Remover";
      btn.addEventListener("click", function () {
        imagensLista.splice(i, 1);
        renderFundoGrid();
        atualizarImagemBase64();
      });
      item.appendChild(img);
      item.appendChild(btn);
      fundoGrid.appendChild(item);
    });
    var faltam = targetCount() - imagensLista.length;
    if (faltam > 0) {
      buscarMaisBtn.hidden = false;
      buscarMaisBtn.textContent = "Buscar mais " + faltam + (faltam > 1 ? " imagens" : " imagem");
    } else {
      buscarMaisBtn.hidden = true;
    }
  }

  // Busca só as imagens (não mexe nas frases nem na legenda)
  buscarImagensBtn.addEventListener("click", function () {
    var busca = (buscaImagem.value || "").trim();
    if (!busca) {
      mostrarAlerta("Informe um tema para buscar imagens.");
      return;
    }
    buscarImagensBtn.disabled = true;
    buscarImagensBtn.textContent = "Buscando…";
    esconderAlerta();
    fetch("/api/buscar_fundos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ busca: busca, n: targetCount(), page: 1 })
    })
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        if (!dados.ok) { mostrarAlerta(dados.erro || "Erro ao buscar imagens."); return; }
        var novas = dados.imagens || [];
        if (!novas.length) { mostrarAlerta("Nenhuma imagem encontrada para essa busca."); return; }
        imagensLista = novas;  // substitui os fundos atuais
        pagina = 1;            // "Buscar mais" continua dessa busca
        atualizarImagemBase64();
        dropzoneTexto.textContent = imagensLista.length + " fundos carregados (um por linha) — remova os que não gostar";
        renderFundoGrid();
        agendarPreview();
      })
      .catch(function () { mostrarAlerta("Não foi possível conectar ao servidor."); })
      .finally(function () {
        buscarImagensBtn.disabled = false;
        buscarImagensBtn.textContent = "Buscar imagens";
      });
  });

  buscarMaisBtn.addEventListener("click", function () {
    var faltam = targetCount() - imagensLista.length;
    if (faltam <= 0) { return; }
    pagina++;
    buscarMaisBtn.disabled = true;
    buscarMaisBtn.textContent = "Buscando…";
    fetch("/api/buscar_fundos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ busca: buscaImagem.value, n: faltam, page: pagina })
    })
      .then(function (r) { return r.json(); })
      .then(function (dados) {
        if (!dados.ok) { mostrarAlerta(dados.erro || "Erro ao buscar."); return; }
        imagensLista = imagensLista.concat(dados.imagens || []);
        renderFundoGrid();
        atualizarImagemBase64();
      })
      .catch(function () { mostrarAlerta("Erro de conexão."); })
      .finally(function () {
        buscarMaisBtn.disabled = false;
      });
  });

  // Regenerar frases (só o campo de frases)
  gerarFrasesBtn.addEventListener("click", function () {
    if (!temaAtual) {
      mostrarAlerta("Escolha um tema no modo automático primeiro.");
      return;
    }
    gerarFrasesBtn.disabled = true;
    gerarFrasesBtn.textContent = "Gerando…";
    fetch("/api/gerar_frases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tema: temaAtual, cta: ctaSelect.value })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { mostrarAlerta(d.erro || "Erro ao gerar frases."); return; }
        textos.value = (d.frases || []).join("\n");
        agendarPreview();
        renderFundoGrid();
      })
      .catch(function () { mostrarAlerta("Erro de conexão."); })
      .finally(function () {
        gerarFrasesBtn.disabled = false;
        gerarFrasesBtn.textContent = "Gerar frases com IA";
      });
  });

  // Regenerar legenda (só o campo de legenda)
  gerarLegendaBtn.addEventListener("click", function () {
    if (!temaAtual) {
      mostrarAlerta("Escolha um tema no modo automático primeiro.");
      return;
    }
    gerarLegendaBtn.disabled = true;
    gerarLegendaBtn.textContent = "Gerando…";
    var frases = (textos.value || "").split("\n").filter(function (l) { return l.trim(); });
    fetch("/api/gerar_legenda", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tema: temaAtual, frases: frases, cta: ctaSelect.value })
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { mostrarAlerta(d.erro || "Erro ao gerar legenda."); return; }
        legendaTexto.value = d.legenda || "";
        resultadoLegenda.hidden = false;
      })
      .catch(function () { mostrarAlerta("Erro de conexão."); })
      .finally(function () {
        gerarLegendaBtn.disabled = false;
        gerarLegendaBtn.textContent = "Gerar legenda com IA";
      });
  });

  carregarTemas();
  carregarVideos();
})();
