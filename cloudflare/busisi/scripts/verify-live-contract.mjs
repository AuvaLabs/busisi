const safeFacilityRegistryHeadings = Object.freeze([
  'DepEd school list is temporarily under maintenance',
  'Official school list is currently blocked',
  'The official school list needs checking',
  'The school list passed, but links still need review',
  'The school-link review did not pass',
  'The checked school links are ready to publish',
  'The checked school links are published',
]);

export const hasSafeFacilityRegistryState = (document) =>
  safeFacilityRegistryHeadings.some((heading) => document.includes(heading));
