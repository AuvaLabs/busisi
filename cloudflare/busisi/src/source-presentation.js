const DBM_ORIGIN = 'https://www.dbm.gov.ph';

export const gaaDocumentsUrl = (fiscalYear) => (
  `${DBM_ORIGIN}/index.php/${fiscalYear}/general-appropriations-act-gaa-fy-${fiscalYear}`
);

export const nepDocumentsUrl = (fiscalYear) => (
  `${DBM_ORIGIN}/index.php/${fiscalYear}/national-expenditure-program-fy-${fiscalYear}`
);

export const deliveryRecordUrl = (contractId) => (
  `/contracts/${encodeURIComponent(contractId)}/`
);

export const budgetRecordUrl = (description, fiscalYear) => (
  `/explore/?${new URLSearchParams({ view: 'budgets', q: description, year: String(fiscalYear) })}`
);
