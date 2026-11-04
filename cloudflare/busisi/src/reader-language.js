const REVIEW_CLASSES = Object.freeze({
  stage_change: Object.freeze({
    label: 'The budget entry changed',
    category: 'The budget changed between documents',
    why_check: 'The amount changed, or the item appears in only one budget document.',
    not_proof: 'This change does not prove who made it, why it happened, or whether it was proper.',
    next_step: 'Compare the NEP and House source pages for this item.',
  }),
  record_contradiction: Object.freeze({
    label: 'The same record says two different things',
    category: 'The record disagrees with itself',
    why_check: 'Two fields that should agree show different information.',
    not_proof: 'A mismatch does not prove that the project is false or that anyone did something wrong.',
    next_step: 'Open the project record and check the fields against newer official documents.',
  }),
  location_review: Object.freeze({
    label: 'The place needs checking',
    category: 'The recorded place may not match',
    why_check: 'The coordinates are missing, repeated, outside broad bounds, or do not match the place label.',
    not_proof: 'A location problem does not prove that the physical project is missing.',
    next_step: 'Compare the place name, coordinates, project images, and official location records.',
  }),
  identity_conflict: Object.freeze({
    label: 'The project ID may point to different records',
    category: 'The project identity needs checking',
    why_check: 'The same identifier may not lead to one clear record, so we may not have the right project.',
    not_proof: 'An ID conflict does not prove that either record is false or unlawful.',
    next_step: 'Compare the contract number, project title, agency, place, and official documents.',
  }),
  coverage_gap: Object.freeze({
    label: 'Some information is missing',
    category: 'We do not have enough information yet',
    why_check: 'A useful source row, coordinate, image, or document was missing or could not be confirmed.',
    not_proof: 'Missing information does not prove that the project or document does not exist.',
    next_step: 'Check the named official source and look for the missing record or document.',
  }),
  repeat_family: Object.freeze({
    label: 'A similar project appears more than once',
    category: 'The project may continue across years',
    why_check: 'A project with a similar name or place appears in another year or record.',
    not_proof: 'Repeated wording does not prove duplicate funding. The records may describe separate phases.',
    next_step: 'Compare the years, work descriptions, amounts, locations, and contract numbers.',
  }),
});

const SIGNALS = Object.freeze({
  status_progress_conflict: Object.freeze({
    label: 'The project says ongoing, but progress says 100%',
    category: 'The record disagrees with itself',
    why_check: 'The status and progress fields should describe the same point in the work.',
    not_proof: 'This mismatch does not prove that the project is unfinished or that anyone did something wrong.',
    next_step: 'Check the latest project update, completion record, and inspection documents.',
  }),
  completed_progress_conflict: Object.freeze({
    label: 'The project says completed, but progress is below 100%',
    category: 'The record disagrees with itself',
    why_check: 'A completed status and a lower progress value should be explained.',
    not_proof: 'This mismatch does not prove poor work, false reporting, or wrongdoing.',
    next_step: 'Check the latest progress report, completion record, and inspection documents.',
  }),
  date_order_conflict: Object.freeze({
    label: 'The dates are out of order',
    category: 'The record disagrees with itself',
    why_check: 'One recorded event appears to happen before an event that should come first.',
    not_proof: 'An unusual date order may be a data-entry or update problem. It does not prove wrongdoing.',
    next_step: 'Compare the notice, start, target, completion, and acceptance dates in signed documents.',
  }),
  nonpositive_active_budget: Object.freeze({
    label: 'An active project has no positive budget',
    category: 'The amount needs checking',
    why_check: 'A project shown as active normally has a budget greater than zero.',
    not_proof: 'A zero or negative value may be a source or accounting issue. It does not prove missing money.',
    next_step: 'Check the project budget, amendments, and source accounting record.',
  }),
  missing_coordinate: Object.freeze({
    label: 'The project has no usable coordinates',
    category: 'We do not have enough information yet',
    why_check: 'Without coordinates, the recorded place cannot be checked on a map.',
    not_proof: 'Missing coordinates do not prove that the project is missing.',
    next_step: 'Check the project page, plans, images, and agency location records.',
  }),
  coordinate_outside_philippines: Object.freeze({
    label: 'The coordinates fall outside broad Philippine bounds',
    category: 'The recorded place may not match',
    why_check: 'The recorded point is outside the broad area used for a first location check.',
    not_proof: 'This may be a typing or coordinate-format error. It does not prove the project location is false.',
    next_step: 'Compare the coordinates with the place name, plans, and geotagged source images.',
  }),
  completed_without_satellite_image: Object.freeze({
    label: 'The record says completed, but this source has no satellite image',
    category: 'We do not have enough information yet',
    why_check: 'A listed image field is missing from the acquired record for a completed project.',
    not_proof: 'A missing image does not prove that work was not completed.',
    next_step: 'Check project images, inspection records, and completion documents.',
  }),
  reused_coordinate: Object.freeze({
    label: 'Several projects use the same coordinates',
    category: 'The recorded place may not match',
    why_check: 'The exact same point appears on more than one project record.',
    not_proof: 'Projects can share a site, entrance, office, or map point. Reuse does not prove duplication.',
    next_step: 'Compare the project titles, places, scopes, images, and site plans.',
  }),
  coordinate_location_conflict: Object.freeze({
    label: 'The coordinates and place name may not agree',
    category: 'The recorded place may not match',
    why_check: 'The same point appears with place labels that may describe different locations.',
    not_proof: 'Office and project labels can differ from map boundaries. This does not prove a false location.',
    next_step: 'Compare the point with official boundaries, the project address, plans, and images.',
  }),
  past_completion_not_complete: Object.freeze({
    label: 'The target date passed, but the project is not marked completed',
    category: 'The schedule needs checking',
    why_check: 'The recorded target date is earlier than the snapshot date, but the status is not completed.',
    not_proof: 'The source may be outdated or the schedule may have changed. This does not prove delay or fault.',
    next_step: 'Check approved extensions, suspension orders, progress reports, and the latest project status.',
  }),
  same_site_repeat_family: Object.freeze({
    label: 'A similar project appears at the same site in another year',
    category: 'The project may continue across years',
    why_check: 'Similar project wording and the same recorded site appear across fiscal years.',
    not_proof: 'The records may describe valid phases or continuing work. This does not prove duplicate funding.',
    next_step: 'Compare the work scope, phase, amount, dates, and contract number for each year.',
  }),
});

const fallback = Object.freeze({
  label: 'This record needs a closer look',
  category: 'Something in the record needs checking',
  why_check: 'A published rule found information that may need an explanation.',
  not_proof: 'A flag is not proof that the project is bad, illegal, or connected to wrongdoing.',
  next_step: 'Open the source record and compare it with current official documents.',
});

export const reviewClassLanguage = (classification) => REVIEW_CLASSES[classification] || fallback;

export const signalLanguage = (code, classification) => (
  SIGNALS[code] || REVIEW_CLASSES[classification] || fallback
);

export const reviewClassEntries = () => Object.entries(REVIEW_CLASSES);
