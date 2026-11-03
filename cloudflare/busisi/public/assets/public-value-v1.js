const summaryRoot = document.querySelector('[data-public-value-summary]');
const indicatorRoot = document.querySelector('[data-value-indicators]');
const filterButtons = [...document.querySelectorAll('[data-value-filter]')];
const increaseRoot = document.querySelector('[data-opportunity-increases]');
const decreaseRoot = document.querySelector('[data-opportunity-decreases]');

const number = new Intl.NumberFormat('en-PH', { maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat('en-PH', { maximumFractionDigits: 0 });

const requestJson = async (path) => {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`request failed with ${response.status}`);
  return response.json();
};

const money = (centavos) => {
  const absolute = Math.abs(centavos);
  if (absolute >= 100_000_000_000_000) return `₱${number.format(centavos / 100_000_000_000_000)}T`;
  if (absolute >= 100_000_000_000) return `₱${number.format(centavos / 100_000_000_000)}B`;
  return `₱${number.format(centavos / 100_000_000)}M`;
};

const formatValue = (row, year) => {
  const value = row[`value_${year}`];
  if (row.unit === 'centavos') return money(value);
  if (row.unit === 'people') return `${number.format(value / 1_000_000)}M`;
  if (row.unit === 'basis_points') return `${number.format(value / 100)}%`;
  const lower = row[`lower_${year}`];
  const upper = row[`upper_${year}`];
  return `${number.format(lower / 100)}–${number.format(upper / 100)}%`;
};

const directionLabel = Object.freeze({
  improving: 'Improving direction',
  pressure: 'Fiscal pressure',
  context: 'Context only',
});

let indicators = [];

const renderIndicators = (category = 'all') => {
  const visible = category === 'all'
    ? indicators
    : indicators.filter((row) => row.category === category);
  indicatorRoot.replaceChildren(...visible.map((row) => {
    const article = document.createElement('article');
    article.className = 'value-indicator';

    const categoryName = document.createElement('span');
    categoryName.className = 'kicker';
    categoryName.textContent = row.category.replace('_', ' ');
    const direction = document.createElement('span');
    direction.className = `direction ${row.direction}`;
    direction.textContent = directionLabel[row.direction];
    const heading = document.createElement('h3');
    heading.textContent = row.label;

    const comparison = document.createElement('div');
    comparison.className = 'value-comparison';
    for (const [year, label] of [[2026, 'FY2026'], [2027, 'FY2027']]) {
      const cell = document.createElement('div');
      const caption = document.createElement('span');
      caption.textContent = label;
      const value = document.createElement('strong');
      value.textContent = formatValue(row, year);
      cell.append(caption, value);
      comparison.append(cell);
      if (year === 2026) {
        const arrow = document.createElement('b');
        arrow.setAttribute('aria-hidden', 'true');
        arrow.textContent = '→';
        comparison.append(arrow);
      }
    }

    const rule = document.createElement('p');
    rule.textContent = row.source_note ? `${row.direction_rule} ${row.source_note}` : row.direction_rule;
    const source = document.createElement('a');
    source.href = row.source_url;
    source.rel = 'external';
    source.textContent = `Open official DBM Table ${row.source_document === 'besf-a1' ? 'A.1' : 'A.2'} · PDF page ${row.source_page}`;
    article.append(categoryName, direction, heading, comparison, rule, source);
    return article;
  }));
};

const renderSummary = (summary) => {
  const cards = [...summaryRoot.querySelectorAll('article')];
  cards[1].querySelector('strong').textContent = `₱${integer.format(summary.expenditure_per_capita_centavos / 100)}`;
  cards[2].querySelector('strong').textContent = `${number.format(summary.revenue_coverage_bps / 100)}%`;
  cards[3].querySelector('strong').textContent = `${summary.improving_count} improving · ${summary.pressure_count} pressure`;
};

const renderMovements = (root, rows) => {
  root.replaceChildren(...rows.map((row) => {
    const item = document.createElement('li');
    const name = document.createElement('strong');
    name.textContent = row.name;
    const value = document.createElement('span');
    value.textContent = `${row.difference_centavos >= 0 ? '+' : '−'}${money(Math.abs(row.difference_centavos))}`;
    item.append(name, value);
    return item;
  }));
};

const renderMovementError = (root) => {
  const item = document.createElement('li');
  item.textContent = 'Agency movements are temporarily unavailable.';
  root.replaceChildren(item);
};

for (const button of filterButtons) {
  button.addEventListener('click', () => {
    for (const candidate of filterButtons) candidate.setAttribute('aria-pressed', String(candidate === button));
    renderIndicators(button.dataset.valueFilter);
  });
}

Promise.all([
  requestJson('/api/v1/public-value-summary'),
  requestJson('/api/v1/public-value-indicators'),
]).then(([summary, indicatorResponse]) => {
  indicators = indicatorResponse.data;
  renderSummary(summary.data);
  renderIndicators();
}).catch(() => {
  indicatorRoot.textContent = 'Official fiscal indicators are temporarily unavailable. Use the DBM source links below.';
});

Promise.all([
  requestJson('/api/v1/agency-budgets?level=heads&direction=increase&sort=difference_desc&limit=5'),
  requestJson('/api/v1/agency-budgets?level=heads&direction=decrease&sort=difference_asc&limit=5'),
]).then(([increases, decreases]) => {
  renderMovements(increaseRoot, increases.data);
  renderMovements(decreaseRoot, decreases.data);
}).catch(() => {
  renderMovementError(increaseRoot);
  renderMovementError(decreaseRoot);
});
