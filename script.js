// Função para alternar o menu lateral no mobile (se necessário)
function toggleSideMenu() {
    var sideNav = document.getElementById("sideNav");
    if (sideNav) {
      if (sideNav.style.width === "250px") {
        sideNav.style.width = "0";
      } else {
        sideNav.style.width = "250px";
      }
    }
  }
  
  // Função para fechar todos os modais e a sobreposição
  function closeAllModals() {
    var modals = document.querySelectorAll('.modal');
    modals.forEach(function(modal) {
      modal.style.display = 'none';
    });
    var overlay = document.getElementById('modalOverlay');
    if (overlay) {
      overlay.style.display = 'none';
    }
  }
  
  // Função para abrir um modal, garantindo que os outros sejam fechados
  function openModal(modalId) {
    closeAllModals(); // Fecha todos os modais antes de abrir o novo
    var modal = document.getElementById(modalId);
    if (modal) {
      modal.style.display = 'block';
      var overlay = document.getElementById('modalOverlay');
      if (overlay) {
        overlay.style.display = 'block';
      }
    }
  }
  
  // Função para fechar um modal específico
  function closeModal(modalId) {
    var modal = document.getElementById(modalId);
    if (modal) {
      modal.style.display = 'none';
    }
    // Verifica se algum outro modal ainda está aberto
    var anyOpen = false;
    var modals = document.querySelectorAll('.modal');
    modals.forEach(function(m) {
      if (m.style.display === 'block') {
        anyOpen = true;
      }
    });
    if (!anyOpen) {
      var overlay = document.getElementById('modalOverlay');
      if (overlay) {
        overlay.style.display = 'none';
      }
    }
  }
  
  // Fecha todos os modais se clicar fora
  window.onclick = function(event) {
    var overlay = document.getElementById('modalOverlay');
    if (event.target === overlay) {
      closeAllModals();
    }
  };
  
  // ----- Infinite Scroll: 20 itens por página -----
const itemsPerPage = 20;
let currentPage = 0;

// Limpa tbody (caso troque de filtro / pesquisa)
function resetTable() {
  const tbody = document.getElementById('tableBody');
  if (tbody) tbody.innerHTML = '';
  currentPage = 0;
}

// Renderiza próximo “lote” de itens
function loadNextItems() {
  if (!window.stockData) return;

  const tbody = document.getElementById('tableBody');
  if (!tbody) return;

  const start = currentPage * itemsPerPage;
  const end   = start + itemsPerPage;
  const items = window.stockData.slice(start, end);

  let html = '';
  items.forEach(item => {
    let classes = [];

    if (item.tipo && item.tipo.toLowerCase() === 'ferramentas') classes.push('ferramenta');
    if (item.nivel_critico != null && item.quantidade <= item.nivel_critico) classes.push('critical');

    html += `
      <tr class="${classes.join(' ')}">
        <td>${item.codigo}</td>
        <td>${item.nome}</td>
        <td>${item.tipo}</td>
        <td>${item.quantidade}</td>
        <td>${item.fabricante || '-'}</td>
        <td>${item.voltagem || '-'}</td>
        <td>${item.nivel_critico ?? '-'}</td>
        ${sessionRole !== 'subusuario'
          ? (sessionRole === 'gerente'
              ? `<td><a href="/delete_inventory/${item.codigo}" onclick="return confirm('Tem certeza?');">🗑️ Excluir</a></td>`
              : '<td>—</td>')
          : ''}
      </tr>`;
  });

  tbody.insertAdjacentHTML('beforeend', html);
  currentPage++;
}

// Inicia scroll
const container = document.getElementById('tableContainer');
if (container) {
  container.addEventListener('scroll', () => {
    if (container.scrollTop + container.clientHeight >= container.scrollHeight) {
      loadNextItems();
    }
  });
  resetTable();
  loadNextItems();
}

