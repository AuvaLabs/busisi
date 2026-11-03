const COMPLETE_STATUS = /complete/i;
const AWARD_STATUS = /award|complete/i;

const actualEvents = (records) => records
  .flatMap((record) => record.events || [])
  .filter((event) => event.date_kind === 'actual');

const eventByStage = (events, stage) => events.find((event) => event.stage === stage) || null;

const eventsOfKind = (records, kind) => records
  .flatMap((record) => record.events || [])
  .filter((event) => event.date_kind === kind);

const procurementAmount = (records) => records.find(
  (record) => Number.isInteger(record.contract_cost_centavos),
) || null;

const awardClaim = (records, events) => records.some(
  (record) => AWARD_STATUS.test(record.procurement_status || ''),
) || Boolean(eventByStage(events, 'notice_of_award'));

const amountCheck = (records, delivery, awardMirror) => {
  const procurement = procurementAmount(records);
  const sourceAmount = Number.isInteger(awardMirror?.contract_amount_centavos)
    ? awardMirror.contract_amount_centavos
    : procurement?.contract_cost_centavos ?? null;
  const sourceLabel = awardMirror
    ? 'Secondary PhilGEPS mirror award amount'
    : procurement ? 'Procurement monitoring report contract amount' : null;
  if (!Number.isInteger(sourceAmount) || !Number.isInteger(delivery?.budget_centavos)) {
    return {
      state: 'gap',
      procurement_centavos: sourceAmount,
      delivery_centavos: delivery?.budget_centavos ?? null,
      difference_centavos: null,
      source_label: sourceLabel,
      label: 'Comparable contract amounts not available in both sources',
    };
  }
  const difference = delivery.budget_centavos - sourceAmount;
  return {
    state: difference === 0 ? 'consistent' : 'question',
    procurement_centavos: sourceAmount,
    delivery_centavos: delivery.budget_centavos,
    difference_centavos: difference,
    source_label: sourceLabel,
    label: awardMirror
      ? difference === 0
        ? 'Mirror award and delivery contract amounts agree'
        : 'Mirror award and delivery contract amounts differ'
      : difference === 0
        ? 'Procurement and delivery contract amounts agree'
        : 'Procurement and delivery contract amounts differ',
  };
};

const question = (code, label, detail, severity = 'review') => ({
  code, label, detail, severity,
});

const statusQuestions = (records, delivery, events) => {
  const questions = [];
  const procurementCompleted = records.some(
    (record) => COMPLETE_STATUS.test(record.procurement_status || ''),
  );
  const deliveryCompleted = COMPLETE_STATUS.test(delivery?.status || '');
  const progressComplete = Number(delivery?.progress) === 100;
  if (procurementCompleted && (!deliveryCompleted || !delivery?.completion_date)) {
    questions.push(question(
      'completion_status_conflict',
      'Completion states differ between official records',
      'The procurement report says completed while the delivery record is not completed or has no completion date.',
    ));
  }
  if (progressComplete && !deliveryCompleted) {
    questions.push(question(
      'progress_status_conflict',
      'Progress and status differ in the delivery record',
      'The delivery snapshot reports 100 percent progress while its status is not completed.',
    ));
  }
  if ((procurementCompleted || deliveryCompleted || progressComplete)
    && !eventByStage(events, 'inspection_acceptance')) {
    questions.push(question(
      'completion_without_inspection_evidence',
      'Completion is reported without acquired inspection evidence',
      'A completion claim is present, but no actual inspection and acceptance event was acquired.',
      'evidence_gap',
    ));
  }
  return questions;
};

const sequenceQuestions = (delivery, events) => {
  const signing = eventByStage(events, 'contract_signing');
  const proceed = eventByStage(events, 'notice_to_proceed');
  const questions = [];
  if (signing && proceed && proceed.event_date < signing.event_date) {
    questions.push(question(
      'notice_to_proceed_before_contract',
      'Notice to Proceed predates contract signing',
      `${proceed.event_date} precedes the recorded contract-signing date ${signing.event_date}.`,
    ));
  }
  if (proceed && delivery?.start_date && delivery.start_date < proceed.event_date) {
    questions.push(question(
      'implementation_before_notice_to_proceed',
      'Implementation start predates Notice to Proceed',
      `${delivery.start_date} precedes the recorded Notice to Proceed date ${proceed.event_date}.`,
    ));
  }
  return questions;
};

const scheduleQuestions = (records) => {
  const planned = eventsOfKind(records, 'planned');
  const actual = eventsOfKind(records, 'actual');
  return planned.flatMap((plan) => {
    const observed = eventByStage(actual, plan.stage);
    if (!observed || observed.event_date === plan.event_date) return [];
    return [question(
      `schedule_variance:${plan.stage}`,
      `${plan.stage.replaceAll('_', ' ')} differs from plan`,
      `Planned ${plan.event_date}; recorded actual ${observed.event_date}.`,
      'schedule_variance',
    )];
  });
};

const evidenceState = (state, label, detail) => ({ state, label, detail });

const normalizedContractor = (value) => String(value || '')
  .replace(/\s*\(\d+\)\s*$/, '')
  .replace(/[^A-Z0-9]+/gi, ' ')
  .trim()
  .toUpperCase();

const awardeeCheck = (awardMirror, delivery) => {
  if (!awardMirror || !delivery?.contractor_name) {
    return evidenceState('gap', 'Comparable awardee and contractor names unavailable', 'No name comparison was made.');
  }
  const matches = normalizedContractor(awardMirror.awardee_name)
    === normalizedContractor(delivery.contractor_name);
  return evidenceState(
    matches ? 'consistent_secondary' : 'question',
    matches ? 'Mirror awardee and delivery contractor names agree' : 'Mirror awardee and delivery contractor names differ',
    'This is a normalized name comparison against a secondary mirror row, not verification of the original award notice.',
  );
};

export const buildContractOutcome = ({ coverage, procurementRecords, delivery, awardMirror = null }) => {
  const records = Array.isArray(procurementRecords) ? procurementRecords : [];
  const events = actualEvents(records);
  const awardLocated = awardClaim(records, events);
  const inspection = eventByStage(events, 'inspection_acceptance');
  const amount = amountCheck(records, delivery, awardMirror);
  const awardee = awardeeCheck(awardMirror, delivery);
  const questions = [
    ...statusQuestions(records, delivery, events),
    ...sequenceQuestions(delivery, events),
    ...scheduleQuestions(records),
  ];
  if (amount.state === 'question') {
    questions.unshift(question(
      'contract_amount_mismatch',
      amount.label,
      'The contract amount in the available award or procurement evidence differs from the value in the delivery snapshot.',
    ));
  }
  if (awardee.state === 'question') {
    questions.push(question(
      'awardee_contractor_name_mismatch',
      awardee.label,
      'The secondary mirror awardee name differs from the contractor name in the DPWH delivery snapshot.',
    ));
  }
  return {
    case_id: coverage?.case_id || null,
    contract_id: coverage?.contract_id || delivery?.contract_id || null,
    fiscal_year: coverage?.fiscal_year || delivery?.fiscal_year || null,
    title: delivery?.description || records[0]?.project_title || '',
    contractor_name: delivery?.contractor_name || '',
    delivery_status: delivery?.status || '',
    delivery_progress: delivery?.progress || '',
    start_date: delivery?.start_date || '',
    completion_date: delivery?.completion_date || '',
    amount_check: amount,
    award_evidence: awardMirror
      ? evidenceState('secondary', 'Versioned award mirror row located', 'The source-file row is retained with revision and row hash, but the original PhilGEPS award page is not archived.')
      : awardLocated
      ? evidenceState('partial', 'Award event or status located', 'The acquired procurement evidence reports an award event or status.')
      : evidenceState('gap', 'No award event acquired', 'No actual award event was located in the acquired procurement evidence.'),
    awardee_evidence: awardMirror
      ? evidenceState('secondary', 'Awardee reported by the PhilGEPS mirror', `${awardMirror.awardee_name}. The original official award artifact is not archived.`)
      : evidenceState('gap', 'Awardee not established by acquired procurement evidence', delivery?.contractor_name
        ? 'A contractor is stated in the DPWH delivery snapshot, but no acquired award artifact independently names the awardee.'
        : 'No acquired award artifact names the awardee.'),
    awardee_check: awardee,
    award_mirror: awardMirror,
    inspection_evidence: inspection
      ? evidenceState('available', 'Inspection and acceptance event located', inspection.event_date)
      : evidenceState('gap', 'No inspection and acceptance record acquired', 'A blank or missing event is preserved as unavailable.'),
    payment_evidence: evidenceState(
      'gap',
      'No project-specific payment record acquired',
      'Appropriations, procurement values, and implementation records are not proof of payment.',
    ),
    questions,
  };
};
