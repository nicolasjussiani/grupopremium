/* Navegação construída somente a partir dos links já liberados no menu. */
(() => {
  'use strict';
  const dialog = document.getElementById('navigation-search');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
  const entries = [];
  const seen = new Set();
  document.querySelectorAll('.sidebar-nav a.nav-item').forEach(link => {
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || seen.has(url.pathname)) return;
    const copy = link.cloneNode(true);
    copy.querySelectorAll('.nav-icon,.nav-badge').forEach(node => node.remove());
    const title = copy.textContent.replace(/\s+/g, ' ').trim();
    const group = link.closest('[data-nav-group]')?.querySelector('summary strong')?.textContent || 'Geral';
    let keywords = `${title} ${group}`;
    if (/colaborador/i.test(title)) keywords += ' funcionário funcionários equipe pessoa';
    if (/folha/i.test(title)) keywords += ' salário salarios pagamento pagamentos vale transporte vt';
    if (/presen/i.test(title)) keywords += ' falta atestado ponto';
    if (/recrutamento/i.test(title)) keywords += ' vaga candidato contratação';
    if (/SESMET|EPI/i.test(title)) keywords += ' segurança equipamentos proteção';
    if (/IP/i.test(title)) keywords += ' liberar rede bloquear acesso';
    entries.push({title, group, keywords: normalize(keywords), path: url.pathname, icon: link.querySelector('.nav-icon')?.textContent || '→'});
    seen.add(url.pathname);
  });
  const storageKey = `premiumbr-favorites-v1:${document.body.dataset.interfaceUser}`;
  let favorites = [];
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '[]');
    if (Array.isArray(saved)) favorites = [...new Set(saved.filter(path => seen.has(path) && path !== '/'))].slice(0, 6);
  } catch (_) { /* Navegação funciona mesmo sem armazenamento local. */ }
  const query = document.getElementById('navigation-query');
  const results = document.getElementById('navigation-results');
  const resultCount = document.getElementById('navigation-result-count');
  const home = document.getElementById('home-shortcuts');
  const homeGrid = document.getElementById('home-shortcuts-grid');
  let opener;

  function star(entry) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'favorite-button';
    button.dataset.favorite = entry.path;
    const selected = favorites.includes(entry.path);
    button.textContent = selected ? '★' : '☆';
    button.setAttribute('aria-pressed', String(selected));
    button.setAttribute('aria-label', `${selected ? 'Remover dos' : 'Adicionar aos'} favoritos: ${entry.title}`);
    button.title = selected ? 'Remover dos favoritos' : 'Adicionar aos favoritos';
    button.addEventListener('click', () => {
      if (!selected && favorites.length >= 6) {
        if (!dialog.open) openSearch(button);
        resultCount.textContent = 'Você já tem 6 favoritos. Remova uma estrela para escolher outra função.';
        return;
      }
      favorites = selected ? favorites.filter(path => path !== entry.path) : [...favorites, entry.path];
      try { localStorage.setItem(storageKey, JSON.stringify(favorites)); } catch (_) { /* Mantém a escolha nesta página. */ }
      const container = button.closest('#navigation-results') ? results : homeGrid;
      renderResults(); renderHome();
      const replacement = Array.from(container?.querySelectorAll('[data-favorite]') || []).find(item => item.dataset.favorite === entry.path);
      (replacement || (dialog.open ? query : document.querySelector('[data-open-navigation]')))?.focus();
    });
    return button;
  }

  function entryLink(entry, className) {
    const link = document.createElement('a');
    link.className = className;
    link.href = entry.path;
    const icon = document.createElement('span');
    icon.className = 'shortcut-icon'; icon.textContent = entry.icon; icon.setAttribute('aria-hidden', 'true');
    const copy = document.createElement('span');
    const title = document.createElement('strong'); title.textContent = entry.title;
    const subtitle = document.createElement('small'); subtitle.textContent = entry.group;
    copy.append(title, subtitle); link.append(icon, copy);
    return link;
  }

  function renderHome() {
    if (!homeGrid || !entries.length) return;
    const available = entries.filter(entry => entry.path !== '/' && entry.group !== 'Geral');
    const representatives = [...new Set(available.map(entry => entry.group))].map(group => available.find(entry => entry.group === group));
    const defaultOrder = [...representatives, ...available.filter(entry => !representatives.includes(entry))];
    const ordered = [...favorites.map(path => available.find(entry => entry.path === path)).filter(Boolean), ...defaultOrder.filter(entry => !favorites.includes(entry.path))];
    homeGrid.replaceChildren();
    ordered.slice(0, 6).forEach(entry => {
      const card = document.createElement('div'); card.className = 'home-shortcut';
      card.append(entryLink(entry, 'home-shortcut-link'), star(entry)); homeGrid.append(card);
    });
    home.hidden = !ordered.length;
  }

  function renderResults() {
    const terms = normalize(query.value).split(/\s+/).filter(Boolean);
    const matches = entries.filter(entry => terms.every(term => entry.keywords.includes(term)));
    matches.sort((a, b) => Number(favorites.includes(b.path)) - Number(favorites.includes(a.path)));
    results.replaceChildren();
    resultCount.textContent = terms.length ? `${matches.length} ${matches.length === 1 ? 'função encontrada' : 'funções encontradas'}` : 'Suas funções disponíveis · favoritos primeiro';
    matches.forEach(entry => {
      const row = document.createElement('div'); row.className = 'navigation-result';
      row.append(entryLink(entry, 'navigation-result-link'));
      if (entry.path !== '/' && entry.group !== 'Geral') row.append(star(entry));
      results.append(row);
    });
    if (!matches.length) {
      const empty = document.createElement('p'); empty.className = 'navigation-empty';
      empty.textContent = 'Nenhuma função encontrada. Tente outro nome, como colaboradores ou compras.'; results.append(empty);
    }
  }

  function openSearch(trigger) {
    opener = trigger || document.activeElement;
    query.value = ''; renderResults();
    if (!dialog.open) dialog.showModal();
    query.focus();
  }
  if (dialog && typeof dialog.showModal === 'function') {
    document.querySelectorAll('[data-open-navigation]').forEach(button => {
      button.hidden = false; button.addEventListener('click', () => openSearch(button));
    });
    document.querySelector('[data-close-navigation]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { if (opener?.isConnected) opener.focus(); });
    dialog.addEventListener('click', event => {
      const box = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
    });
    query.addEventListener('input', renderResults);
    query.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') { event.preventDefault(); results.querySelector('a')?.focus(); }
      if (event.key === 'Enter') { event.preventDefault(); results.querySelector('a')?.click(); }
    });
    document.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openSearch(); }
    });
    renderHome();
  }

  // Campos e erros: sem alterar envio, validação ou valores dos formulários.
  document.querySelectorAll('#conteudo-principal form').forEach((form, formIndex) => {
    const errors = Array.from(form.querySelectorAll('.field-error,.form-error,.errorlist')).filter(error => error.textContent.trim());
    if (!errors.length) return;
    const summary = document.createElement('div'); summary.className = 'form-error-summary'; summary.setAttribute('role', 'alert');
    const title = document.createElement('strong'); title.textContent = 'Confira os campos abaixo para continuar'; summary.append(title);
    const list = document.createElement('ul');
    errors.forEach((error, index) => {
      const group = error.closest('.form-group');
      const field = group?.querySelector('input:not([type=hidden]),select,textarea');
      const item = document.createElement('li');
      if (field) {
        if (!field.id) field.id = `interface-field-${formIndex}-${index}`;
        if (!error.id) error.id = `interface-error-${formIndex}-${index}`;
        field.setAttribute('aria-invalid', 'true');
        field.setAttribute('aria-describedby', `${field.getAttribute('aria-describedby') || ''} ${error.id}`.trim());
        const link = document.createElement('a'); link.href = `#${field.id}`;
        link.textContent = `${group.querySelector('label')?.textContent.replace('*', '').trim() || 'Campo'}: ${error.textContent.trim()}`;
        link.addEventListener('click', event => {
          event.preventDefault(); let ancestor = field.parentElement;
          while (ancestor) { if (ancestor.tagName === 'DETAILS') ancestor.open = true; ancestor = ancestor.parentElement; }
          field.focus(); field.scrollIntoView({block: 'center'});
        });
        item.append(link);
      } else item.textContent = error.textContent.trim();
      list.append(item);
    });
    summary.append(list); form.prepend(summary);
  });

  const ipFilters = document.getElementById('ip-filters');
  if (ipFilters) {
    ipFilters.hidden = false;
    const ipQuery = document.getElementById('ip-list-search');
    const ipStatus = document.getElementById('ip-list-status');
    const ipCount = document.getElementById('ip-filter-result');
    const rows = Array.from(document.querySelectorAll('[data-ip-status]'));
    const searchable = rows.map(row => ({row, text: normalize(row.textContent)}));
    function filterIPs() {
      const terms = normalize(ipQuery.value).split(/\s+/).filter(Boolean);
      let visible = 0;
      searchable.forEach(({row, text}) => {
        row.hidden = !((ipStatus.value === 'todos' || ipStatus.value === row.dataset.ipStatus) && terms.every(term => text.includes(term)));
        if (!row.hidden) visible++;
      });
      ipCount.hidden = false;
      ipCount.textContent = visible ? `${visible} ${visible === 1 ? 'rede encontrada' : 'redes encontradas'}` : 'Nenhuma rede encontrada. Tente outro nome ou limpe os filtros.';
    }
    ipQuery.addEventListener('input', filterIPs); ipStatus.addEventListener('change', filterIPs);
    document.getElementById('ip-clear-filters').addEventListener('click', () => { ipQuery.value = ''; ipStatus.value = 'todos'; filterIPs(); ipQuery.focus(); });
  }

  document.querySelectorAll('.table-wrap').forEach(wrapper => {
    const hint = document.createElement('p'); hint.className = 'table-scroll-hint';
    hint.textContent = '↔ Deslize a tabela para ver as outras colunas.';
    wrapper.before(hint);
    function update() {
      const overflow = wrapper.scrollWidth > wrapper.clientWidth + 2;
      hint.hidden = !overflow;
      if (overflow) { wrapper.tabIndex = 0; wrapper.setAttribute('role', 'region'); wrapper.setAttribute('aria-label', 'Tabela com rolagem horizontal'); }
      else { wrapper.removeAttribute('tabindex'); wrapper.removeAttribute('role'); wrapper.removeAttribute('aria-label'); }
    }
    update(); if ('ResizeObserver' in window) new ResizeObserver(update).observe(wrapper);
  });
})();
