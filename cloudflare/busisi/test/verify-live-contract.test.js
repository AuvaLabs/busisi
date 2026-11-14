import assert from 'node:assert/strict';
import test from 'node:test';

import { hasSafeFacilityRegistryState } from '../scripts/verify-live-contract.mjs';

test('accepts every reader-safe facility registry heading', () => {
  for (const heading of [
    'DepEd school list is temporarily under maintenance',
    'Official school list is currently blocked',
    'The official school list needs checking',
    'The school list passed, but links still need review',
    'The school-link review did not pass',
    'The checked school links are ready to publish',
    'The checked school links are published',
  ]) {
    assert.equal(hasSafeFacilityRegistryState(`<h2>${heading}</h2>`), true, heading);
  }
});

test('rejects a page without a recognized facility registry state', () => {
  assert.equal(hasSafeFacilityRegistryState('<h2>Unknown source state</h2>'), false);
});
