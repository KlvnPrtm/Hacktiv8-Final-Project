"use strict";

(() => {
  const form = document.querySelector("#chat-form");
  const input = document.querySelector("#message");
  const send = document.querySelector("#send");
  const messages = document.querySelector("#messages");
  const welcome = document.querySelector("#welcome");
  const scrollArea = document.querySelector("#scroll-area");
  const status = document.querySelector("#status");
  const dialog = document.querySelector("#reset-dialog");
  const newChatButtons = [...document.querySelectorAll("[data-new-chat]")];
  const configured = form.dataset.configured === "true";
  let history = [];
  let pending = null;
  let busy = false;
  let errorCard = null;

  function updateInput() {
    const count = [...input.value].length;
    document.querySelector("#char-count").textContent = `${count.toLocaleString("id-ID")} / 4.000`;
    send.disabled = busy || !!pending || !configured || !input.value.trim();
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  }

  function setBusy(value) {
    busy = value;
    messages.setAttribute("aria-busy", String(value));
    newChatButtons.forEach(button => { button.disabled = value; });
    document.querySelectorAll("input[name=detail]").forEach(radio => { radio.disabled = value || !!pending; });
    input.disabled = value || !!pending;
    document.querySelectorAll("[data-prompt]").forEach(button => { button.disabled = value || !!pending; });
    updateInput();
  }

  function scrollToEnd() {
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }

  function addMessage(role, content, html) {
    const article = document.createElement("article");
    article.className = `message ${role}-message`;
    const label = document.createElement("div");
    label.className = "message-label";
    if (role === "assistant") {
      const icon = document.createElement("img");
      icon.src = document.querySelector("link[rel=icon]").href;
      icon.alt = "";
      label.append(icon);
    }
    label.append(document.createTextNode(role === "user" ? "Kamu" : "Teman Data"));
    const body = document.createElement("div");
    body.className = "message-body";
    if (role === "assistant") {
      // Only the backend's Markdown renderer supplies this sanitized HTML.
      body.innerHTML = html;
      body.querySelectorAll("pre").forEach(pre => {
        const code = pre.querySelector("code");
        const text = code ? code.textContent : pre.textContent;
        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = "code-copy";
        copy.textContent = "Salin kode";
        copy.addEventListener("click", () => copyText(text, copy, "Salin kode"));
        pre.append(copy);
      });
      body.querySelectorAll("table").forEach(table => {
        const wrapper = document.createElement("div");
        wrapper.className = "table-scroll";
        wrapper.tabIndex = 0;
        wrapper.setAttribute("role", "region");
        wrapper.setAttribute("aria-label", "Tabel jawaban, geser untuk melihat semua kolom");
        table.replaceWith(wrapper);
        wrapper.append(table);
      });
    } else {
      body.textContent = content;
    }
    article.append(label, body);
    if (role === "assistant") {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "copy-answer";
      copy.textContent = "Salin jawaban";
      copy.addEventListener("click", () => copyText(content, copy, "Salin jawaban"));
      article.append(copy);
    }
    messages.append(article);
    return article;
  }

  async function copyText(text, button, originalLabel) {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const helper = document.createElement("textarea");
        helper.value = text;
        helper.className = "sr-only";
        helper.setAttribute("aria-hidden", "true");
        document.body.append(helper);
        helper.select();
        const copied = document.execCommand("copy");
        helper.remove();
        button.focus();
        if (!copied) throw new Error("copy_failed");
      }
      button.textContent = "Tersalin";
      status.textContent = "Berhasil disalin.";
    } catch {
      button.textContent = "Gagal menyalin";
      status.textContent = "Pilih teks, lalu salin manual.";
    }
    window.setTimeout(() => { button.textContent = originalLabel; }, 2200);
  }

  function showError(message) {
    errorCard = document.createElement("div");
    errorCard.className = "error-card";
    errorCard.setAttribute("role", "alert");
    const description = document.createElement("p");
    description.textContent = message;
    const actions = document.createElement("div");
    actions.className = "error-actions";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "Coba lagi";
    retry.addEventListener("click", requestReply);
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Ubah pesan";
    edit.addEventListener("click", () => {
      if (busy || !pending) return;
      input.value = pending.message;
      pending.element.remove();
      pending = null;
      errorCard.remove();
      errorCard = null;
      if (!history.length) { welcome.hidden = false; messages.hidden = true; }
      status.textContent = "Pesan bisa kamu ubah.";
      setBusy(false);
      input.focus();
    });
    actions.append(retry, edit);
    errorCard.append(description, actions);
    messages.append(errorCard);
  }

  async function requestReply() {
    if (busy || !pending) return;
    if (errorCard) { errorCard.remove(); errorCard = null; }
    setBusy(true);
    status.textContent = "Sedang menyiapkan jawaban…";
    const loading = document.createElement("div");
    loading.className = "loading-message";
    const dot = document.createElement("span");
    dot.className = "loading-dot";
    dot.setAttribute("aria-hidden", "true");
    loading.append(dot, document.createTextNode("Sebentar, kita bahas bareng…"));
    messages.append(loading);
    scrollToEnd();
    const controller = new AbortController();
    // The provider timeout is 60s; allow time for the backend error response.
    const timer = window.setTimeout(() => controller.abort(), 65000);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: pending.message, history: history.slice(-12), detail: pending.detail }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.error?.message || "Jawaban belum bisa dimuat. Coba lagi sebentar.");
      if (typeof data?.reply !== "string" || !data.reply.trim() || typeof data?.html !== "string" || !data.html.trim()) {
        throw new Error("Jawaban kosong atau tidak terbaca. Coba kirim ulang pesanmu.");
      }
      addMessage("assistant", data.reply, data.html);
      history.push({ role: "user", content: pending.message }, { role: "assistant", content: data.reply });
      history = history.slice(-12);
      pending = null;
      status.textContent = "Jawaban siap.";
    } catch (error) {
      const text = error.name === "AbortError" ? "Jawaban terlalu lama. Coba lagi sebentar." : error instanceof TypeError ? "Koneksi terputus. Pastikan aplikasi masih berjalan, lalu coba lagi." : error.message;
      showError(text);
      status.textContent = "Pesan belum terjawab.";
    } finally {
      window.clearTimeout(timer);
      loading.remove();
      setBusy(false);
      scrollToEnd();
      if (!pending) input.focus();
    }
  }

  form.addEventListener("submit", event => {
    event.preventDefault();
    const message = input.value.trim();
    if (busy || pending || !configured || !message || [...message].length > 4000) return;
    const detail = document.querySelector("input[name=detail]:checked").value;
    welcome.hidden = true;
    messages.hidden = false;
    const element = addMessage("user", message);
    pending = { message, detail, element };
    input.value = "";
    requestReply();
  });
  input.addEventListener("input", updateInput);
  input.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!send.disabled) form.requestSubmit();
    }
  });
  document.querySelectorAll("[data-prompt]").forEach(button => {
    button.addEventListener("click", () => {
      input.value = button.dataset.prompt.replaceAll("\\n", "\n");
      updateInput();
      input.focus();
    });
  });
  function resetChat() {
    history = [];
    pending = null;
    errorCard = null;
    messages.replaceChildren();
    messages.hidden = true;
    welcome.hidden = false;
    input.value = "";
    status.textContent = "Obrolan baru dimulai.";
    document.querySelector("input[value=singkat]").checked = true;
    setBusy(false);
    scrollArea.scrollTop = 0;
    input.focus();
  }
  newChatButtons.forEach(button => {
    button.addEventListener("click", () => {
      if (busy) return;
      if (history.length || pending || input.value.trim()) {
        dialog.returnValue = "cancel";
        dialog.showModal();
      } else resetChat();
    });
  });
  dialog.addEventListener("close", () => {
    if (dialog.returnValue === "reset") resetChat();
  });
  updateInput();
})();
