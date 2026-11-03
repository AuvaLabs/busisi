const appendText = (parent, tag, value, className) => {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  parent.append(element);
  return element;
};

const representative = (parent, seat) => {
  const row = document.createElement('li');
  appendText(row, 'strong', seat.label);
  const name = seat.representative_name || 'Representative not stated';
  if (seat.representative_profile_url) {
    const link = appendText(row, 'a', name);
    link.href = seat.representative_profile_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
  } else {
    appendText(row, 'span', name);
  }
  if (seat.representative_status === 'ambiguous' && seat.representative_status_note) {
    appendText(row, 'small', seat.representative_status_note);
  }
  parent.append(row);
};

export const renderDistrictContext = (context) => {
  const block = document.createElement('section');
  block.className = `district-context ${context?.classification || 'unassigned'}`;
  appendText(block, 'span', 'Congressional district context', 'district-context-label');
  if (!context || context.classification === 'unassigned') {
    appendText(block, 'strong', 'No district attribution from the listed office');
  } else {
    const shared = context.classification === 'shared_office';
    appendText(
      block,
      'strong',
      shared
        ? `Shared DPWH office serves ${context.districts.length} districts`
        : context.districts[0].label,
    );
    const list = document.createElement('ul');
    context.districts.forEach((seat) => representative(list, seat));
    block.append(list);
  }
  appendText(
    block,
    'small',
    context?.limitation || 'District context is unavailable. No attribution was inferred.',
    'district-context-limit',
  );
  return block;
};
