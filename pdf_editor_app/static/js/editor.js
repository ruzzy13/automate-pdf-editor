(function () {
  "use strict";

  const ZOOM_MIN = 0.25;
  const ZOOM_MAX = 4.0;
  const ZOOM_STEP = 0.15;
  const THUMB_SCALE = 0.22;

  pdfjsLib.GlobalWorkerOptions.workerSrc = window.PDFJS_WORKER_SRC;

  const el = {
    uploadOverlay: document.getElementById("upload-overlay"),
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file-input"),
    newFileInput: document.getElementById("new-file-input"),

    app: document.getElementById("app"),
    sidebar: document.getElementById("sidebar"),
    canvasScroll: document.getElementById("canvas-scroll"),
    canvasStack: document.getElementById("canvas-stack"),

    prevPageBtn: document.getElementById("prev-page-btn"),
    nextPageBtn: document.getElementById("next-page-btn"),
    pageNumInput: document.getElementById("page-num-input"),
    pageCountLabel: document.getElementById("page-count-label"),

    zoomOutBtn: document.getElementById("zoom-out-btn"),
    zoomInBtn: document.getElementById("zoom-in-btn"),
    zoomSelect: document.getElementById("zoom-select"),
    fitWidthBtn: document.getElementById("fit-width-btn"),

    searchInput: document.getElementById("search-input"),
    searchPrevBtn: document.getElementById("search-prev-btn"),
    searchNextBtn: document.getElementById("search-next-btn"),
    searchMatchCount: document.getElementById("search-match-count"),

    toggleDrawerBtn: document.getElementById("toggle-drawer-btn"),
    replaceDrawer: document.getElementById("replace-drawer"),
    replaceForm: document.getElementById("replace-form"),
    tabButtons: document.querySelectorAll(".tab-btn"),
    panelManual: document.getElementById("panel-manual"),
    panelAuto: document.getElementById("panel-auto"),
    applyBtn: document.getElementById("apply-btn"),
    applySpinner: document.getElementById("apply-spinner"),
    formErrors: document.getElementById("form-errors"),

    downloadBtn: document.getElementById("download-btn"),
    filenameLabel: document.getElementById("filename-label"),

    toast: document.getElementById("toast"),
  };

  const state = {
    pdfDoc: null,           
    pageCache: new Map(),   
    textCache: new Map(),   
    totalPages: 0,
    currentPage: 1,
    zoom: 1.0,
    currentPdfBlob: null,   
    filename: "document.pdf",
    renderGeneration: 0,    
    matches: [],            
    matchIndex: -1,
    observer: null,
  };

  function getCsrfToken() {
    const input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function showToast(message, isError) {
    el.toast.textContent = message;
    el.toast.classList.toggle("error", !!isError);
    el.toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => el.toast.classList.remove("show"), 3200);
  }

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
  }

  function bindUploadZone(inputEl, dropzoneEl) {
    dropzoneEl.addEventListener("click", () => inputEl.click());
    inputEl.addEventListener("change", () => {
      if (inputEl.files && inputEl.files[0]) handleNewFile(inputEl.files[0]);
    });
    ["dragover", "dragleave", "drop"].forEach((evt) => {
      dropzoneEl.addEventListener(evt, (e) => {
        e.preventDefault();
        dropzoneEl.classList.toggle("drag-over", evt === "dragover");
      });
    });
    dropzoneEl.addEventListener("drop", (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleNewFile(e.dataTransfer.files[0]);
      }
    });
  }

  async function handleNewFile(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showToast("File harus berformat .pdf", true);
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      showToast("Ukuran file melebihi batas 15MB", true);
      return;
    }

    try {
      await validateOnServer(file);
    } catch (err) {
      showToast(err.message || "File tidak valid", true);
      return;
    }

    state.filename = file.name;
    await loadPdf(file);
    el.uploadOverlay.classList.add("hidden");
  }

  async function validateOnServer(file) {
    const fd = new FormData();
    fd.append("pdf_file", file);
    const resp = await fetch(window.API_UPLOAD_URL, {
      method: "POST",
      headers: { "X-CSRFToken": getCsrfToken() },
      body: fd,
    });
    const data = await resp.json();
    if (!data.ok) {
      const firstError = Object.values(data.errors || {})[0];
      throw new Error(Array.isArray(firstError) ? firstError[0] : "File tidak valid.");
    }
    return data;
  }

  async function loadPdf(blobOrFile, keepPageAndZoom) {
    const prevPage = keepPageAndZoom ? state.currentPage : 1;

    state.currentPdfBlob = blobOrFile;
    const arrayBuffer = await blobOrFile.arrayBuffer();
    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
    const pdfDoc = await loadingTask.promise;

    state.pdfDoc = pdfDoc;
    state.totalPages = pdfDoc.numPages;
    state.pageCache.clear();
    state.textCache.clear();
    state.matches = [];
    state.matchIndex = -1;
    updateMatchCountLabel();

    el.pageCountLabel.textContent = "/ " + state.totalPages;
    el.filenameLabel.textContent = state.filename;

    await renderThumbnails();
    if (!keepPageAndZoom) {
      state.zoom = await computeFitWidthScale();
    }
    await renderAllPages(state.zoom);

    state.currentPage = clamp(prevPage, 1, state.totalPages);
    goToPage(state.currentPage, "auto");
    syncZoomUi();
    setupIntersectionObserver();
  }

  async function getPage(pageNum) {
    if (!state.pageCache.has(pageNum)) {
      const page = await state.pdfDoc.getPage(pageNum);
      state.pageCache.set(pageNum, page);
    }
    return state.pageCache.get(pageNum);
  }

  async function computeFitWidthScale() {
    const page = await getPage(1);
    const viewport = page.getViewport({ scale: 1 });
    const containerWidth = el.canvasScroll.clientWidth - 48; 
    return clamp(containerWidth / viewport.width, ZOOM_MIN, ZOOM_MAX);
  }

  async function renderAllPages(scale) {
    const generation = ++state.renderGeneration;
    el.canvasStack.innerHTML = "";

    for (let pageNum = 1; pageNum <= state.totalPages; pageNum++) {
      if (generation !== state.renderGeneration) return; 

      const page = await getPage(pageNum);
      const viewport = page.getViewport({ scale });

      const wrapper = document.createElement("div");
      wrapper.className = "page-wrapper";
      wrapper.dataset.pageNumber = String(pageNum);
      wrapper.style.width = viewport.width + "px";
      wrapper.style.height = viewport.height + "px";

      const label = document.createElement("div");
      label.className = "page-label font-mono";
      label.textContent = "Halaman " + pageNum;
      wrapper.appendChild(label);

      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      wrapper.appendChild(canvas);

      el.canvasStack.appendChild(wrapper);

      const ctx = canvas.getContext("2d");
      await page.render({ canvasContext: ctx, viewport }).promise;

      if (generation !== state.renderGeneration) return;
    }

    if (state.matches.length) {
      renderHighlightsForVisiblePages();
    }
  }

  async function renderThumbnails() {
    el.sidebar.innerHTML = "";
    for (let pageNum = 1; pageNum <= state.totalPages; pageNum++) {
      const page = await getPage(pageNum);
      const viewport = page.getViewport({ scale: THUMB_SCALE });

      const wrapper = document.createElement("div");
      wrapper.className = "thumb-wrapper" + (pageNum === state.currentPage ? " active" : "");
      wrapper.dataset.pageNumber = String(pageNum);

      const box = document.createElement("div");
      box.className = "thumb-canvas-box";
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      box.appendChild(canvas);
      wrapper.appendChild(box);

      const label = document.createElement("div");
      label.className = "thumb-label";
      label.textContent = String(pageNum);
      wrapper.appendChild(label);

      wrapper.addEventListener("click", () => goToPage(pageNum, "smooth"));
      el.sidebar.appendChild(wrapper);

      const ctx = canvas.getContext("2d");
      page.render({ canvasContext: ctx, viewport });
    }
  }

  function setActiveThumb(pageNum) {
    el.sidebar.querySelectorAll(".thumb-wrapper").forEach((n) => {
      n.classList.toggle("active", n.dataset.pageNumber === String(pageNum));
    });
  }

  function goToPage(pageNum, behavior) {
    pageNum = clamp(pageNum, 1, state.totalPages);
    const wrapper = el.canvasStack.querySelector('[data-page-number="' + pageNum + '"]');
    if (wrapper) {
      wrapper.scrollIntoView({ behavior: behavior || "smooth", block: "start" });
    }
    state.currentPage = pageNum;
    el.pageNumInput.value = pageNum;
    setActiveThumb(pageNum);
  }

  function setupIntersectionObserver() {
    if (state.observer) state.observer.disconnect();
    state.observer = new IntersectionObserver(
      (entries) => {
        let best = null;
        entries.forEach((entry) => {
          if (entry.isIntersecting && (!best || entry.intersectionRatio > best.intersectionRatio)) {
            best = entry;
          }
        });
        if (best) {
          const pageNum = Number(best.target.dataset.pageNumber);
          state.currentPage = pageNum;
          el.pageNumInput.value = pageNum;
          setActiveThumb(pageNum);
        }
      },
      { root: el.canvasScroll, threshold: [0.25, 0.5, 0.75] }
    );
    el.canvasStack.querySelectorAll(".page-wrapper").forEach((w) => state.observer.observe(w));
  }

  async function setZoom(newZoom) {
    state.zoom = clamp(newZoom, ZOOM_MIN, ZOOM_MAX);
    await renderAllPages(state.zoom);
    goToPage(state.currentPage, "auto");
    setupIntersectionObserver();
    syncZoomUi();
  }

  function syncZoomUi() {
    const pct = Math.round(state.zoom * 100);
    const presetOptions = Array.from(el.zoomSelect.options).map((o) => o.value);
    el.zoomSelect.value = presetOptions.includes(String(pct)) ? String(pct) : "";
  }

  async function getTextItems(pageNum) {
    if (!state.textCache.has(pageNum)) {
      const page = await getPage(pageNum);
      const content = await page.getTextContent();
      state.textCache.set(pageNum, content.items);
    }
    return state.textCache.get(pageNum);
  }

  async function runSearch(query) {
    clearHighlights();
    state.matches = [];
    state.matchIndex = -1;

    const q = query.trim().toLowerCase();
    if (!q) {
      updateMatchCountLabel();
      return;
    }

    for (let pageNum = 1; pageNum <= state.totalPages; pageNum++) {
      const items = await getTextItems(pageNum);
      items.forEach((item) => {
        if (item.str && item.str.toLowerCase().includes(q)) {
          state.matches.push({ pageNum: pageNum, item: item });
        }
      });
    }

    updateMatchCountLabel();
    if (state.matches.length) {
      state.matchIndex = 0;
      await highlightCurrentMatch();
    } else {
      showToast('Tidak ada hasil untuk "' + query + '"', true);
    }
  }

  function updateMatchCountLabel() {
    if (!state.matches.length) {
      el.searchMatchCount.textContent = "0/0";
    } else {
      el.searchMatchCount.textContent = (state.matchIndex + 1) + "/" + state.matches.length;
    }
    el.searchPrevBtn.disabled = state.matches.length === 0;
    el.searchNextBtn.disabled = state.matches.length === 0;
  }

  async function findNext() {
    if (!state.matches.length) return;
    state.matchIndex = (state.matchIndex + 1) % state.matches.length;
    await highlightCurrentMatch();
  }

  async function findPrev() {
    if (!state.matches.length) return;
    state.matchIndex = (state.matchIndex - 1 + state.matches.length) % state.matches.length;
    await highlightCurrentMatch();
  }

  function clearHighlights() {
    document.querySelectorAll(".search-highlight").forEach((n) => n.remove());
  }

  async function renderHighlightsForVisiblePages() {
    clearHighlights();
    for (let i = 0; i < state.matches.length; i++) {
      await drawHighlight(state.matches[i], i === state.matchIndex);
    }
  }

  async function drawHighlight(match, isCurrent) {
    const wrapper = el.canvasStack.querySelector('[data-page-number="' + match.pageNum + '"]');
    if (!wrapper) return;

    const page = await getPage(match.pageNum);
    const viewport = page.getViewport({ scale: state.zoom });

    const tx = pdfjsLib.Util.transform(viewport.transform, match.item.transform);
    const fontHeight = Math.hypot(tx[2], tx[3]);
    const left = tx[4];
    const top = tx[5] - fontHeight;
    const width = match.item.width * state.zoom;
    const height = fontHeight * 1.15;

    const box = document.createElement("div");
    box.className = "search-highlight" + (isCurrent ? " current" : "");
    box.style.left = left + "px";
    box.style.top = top + "px";
    box.style.width = Math.max(width, 4) + "px";
    box.style.height = Math.max(height, 4) + "px";
    wrapper.appendChild(box);
  }

  async function highlightCurrentMatch() {
    updateMatchCountLabel();
    await renderHighlightsForVisiblePages();
    const match = state.matches[state.matchIndex];
    if (match) goToPage(match.pageNum, "smooth");
  }

  function bindTabs() {
    el.tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        el.tabButtons.forEach((b) => b.setAttribute("aria-selected", "false"));
        btn.setAttribute("aria-selected", "true");
        el.panelManual.classList.toggle("hidden", btn.dataset.tab !== "manual");
        el.panelAuto.classList.toggle("hidden", btn.dataset.tab !== "auto");
      });
    });
  }

  function setApplyLoading(isLoading) {
    el.applyBtn.disabled = isLoading;
    el.applySpinner.classList.toggle("hidden", !isLoading);
  }

  function renderFormErrors(errors) {
    el.formErrors.innerHTML = "";
    if (!errors) return;
    const messages = [];
    Object.entries(errors).forEach(function (entry) {
      const field = entry[0], msgs = entry[1];
      msgs.forEach(function (m) {
        messages.push(field === "__all__" ? m : field + ": " + m);
      });
    });
    messages.forEach(function (m) {
      const p = document.createElement("p");
      p.className = "field-error";
      p.textContent = m;
      el.formErrors.appendChild(p);
    });
  }

  async function submitReplace(e) {
    e.preventDefault();
    if (!state.currentPdfBlob) {
      showToast("Unggah PDF terlebih dahulu.", true);
      return;
    }

    renderFormErrors(null);
    setApplyLoading(true);

    const fd = new FormData(el.replaceForm);
    fd.set("pdf_file", state.currentPdfBlob, state.filename);

    try {
      const resp = await fetch(window.API_REPLACE_URL, {
        method: "POST",
        headers: { "X-CSRFToken": getCsrfToken() },
        body: fd,
      });

      if (!resp.ok) {
        const data = await resp.json();
        renderFormErrors(data.errors);
        showToast("Gagal memproses PDF.", true);
        return;
      }

      const blob = await resp.blob();
      const newFilename = resp.headers.get("X-Filename") || state.filename;
      state.filename = newFilename;

      await loadPdf(blob, true);
      showToast("Berhasil diperbarui.");
      el.replaceForm.reset();
      const stopSymbolInput = document.getElementById("stop_symbol");
      if (stopSymbolInput) stopSymbolInput.value = "%";
    } catch (err) {
      showToast("Terjadi kesalahan jaringan.", true);
    } finally {
      setApplyLoading(false);
    }
  }

  function downloadCurrentPdf() {
    if (!state.currentPdfBlob) return;
    const url = URL.createObjectURL(state.currentPdfBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = state.filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
  }

  function bindToolbar() {
    el.prevPageBtn.addEventListener("click", () => goToPage(state.currentPage - 1, "smooth"));
    el.nextPageBtn.addEventListener("click", () => goToPage(state.currentPage + 1, "smooth"));
    el.pageNumInput.addEventListener("change", () => {
      const n = parseInt(el.pageNumInput.value, 10);
      if (!isNaN(n)) goToPage(n, "smooth");
    });

    el.zoomInBtn.addEventListener("click", () => setZoom(state.zoom + ZOOM_STEP));
    el.zoomOutBtn.addEventListener("click", () => setZoom(state.zoom - ZOOM_STEP));
    el.zoomSelect.addEventListener("change", () => {
      if (el.zoomSelect.value) setZoom(Number(el.zoomSelect.value) / 100);
    });
    el.fitWidthBtn.addEventListener("click", async () => {
      const scale = await computeFitWidthScale();
      setZoom(scale);
    });

    let searchDebounce;
    el.searchInput.addEventListener("input", () => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => runSearch(el.searchInput.value), 350);
    });
    el.searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.shiftKey ? findPrev() : findNext();
      }
    });
    el.searchNextBtn.addEventListener("click", findNext);
    el.searchPrevBtn.addEventListener("click", findPrev);

    el.toggleDrawerBtn.addEventListener("click", () => {
      el.replaceDrawer.classList.toggle("collapsed");
    });

    el.downloadBtn.addEventListener("click", downloadCurrentPdf);
  }

  function init() {
    bindUploadZone(el.fileInput, el.dropzone);
    if (el.newFileInput) {
      el.newFileInput.addEventListener("change", () => {
        if (el.newFileInput.files && el.newFileInput.files[0]) handleNewFile(el.newFileInput.files[0]);
      });
    }
    bindToolbar();
    bindTabs();
    el.replaceForm.addEventListener("submit", submitReplace);
  }

  document.addEventListener("DOMContentLoaded", init);
})();