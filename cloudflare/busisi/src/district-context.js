const LIMITATION = 'District context is inferred only from the listed DPWH office. It does not show who requested, sponsored, controlled, or is responsible for a project or amount.';

const safeDistricts = (value) => {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

export const districtContext = (row) => {
  const classification = row.district_classification;
  const districts = safeDistricts(row.districts_json);
  if (!['single_district', 'shared_office'].includes(classification) || !districts.length) {
    return Object.freeze({
      classification: 'unassigned',
      office_name: row.district_office_name || '',
      districts: [],
      limitation: LIMITATION,
    });
  }
  return Object.freeze({
    classification,
    office_name: row.district_office_name,
    districts,
    limitation: LIMITATION,
  });
};

export const DISTRICT_SELECT = `district.classification AS district_classification,
  district.office_name AS district_office_name, district.districts_json`;

export const districtOfficeJoin = (officeExpression) => `LEFT JOIN district_office_attributions district
  ON LOWER(TRIM(${officeExpression})) = district.office_key`;
