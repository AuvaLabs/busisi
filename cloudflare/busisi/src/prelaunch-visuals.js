export const evidenceOrbit = `
  <figure class="evidence-orbit" aria-label="Evidence moves from official source to reviewed publication">
    <svg viewBox="0 0 620 520" role="img" aria-labelledby="orbit-title orbit-desc">
      <title id="orbit-title">The Busisi evidence path</title>
      <desc id="orbit-desc">Five connected stages move a public record from its official source through preservation, matching, review, and publication.</desc>
      <path class="orbit-track" d="M118 104C243 30 443 55 508 184c65 129-17 270-151 286-134 16-268-77-243-210 25-133 228-177 342-70 85 80 46 196-56 226"/>
      <path class="orbit-flow" d="M118 104C243 30 443 55 508 184c65 129-17 270-151 286-134 16-268-77-243-210 25-133 228-177 342-70 85 80 46 196-56 226"/>
      <g class="orbit-node" transform="translate(118 104)"><circle r="42"/><text y="-4">01</text><text class="node-label" y="70">Official source</text></g>
      <g class="orbit-node" transform="translate(508 184)"><circle r="42"/><text y="-4">02</text><text class="node-label" y="70">Archived copy</text></g>
      <g class="orbit-node" transform="translate(357 470)"><circle r="42"/><text y="-4">03</text><text class="node-label" y="70">Identity match</text></g>
      <g class="orbit-node" transform="translate(114 260)"><circle r="42"/><text y="-4">04</text><text class="node-label" x="-16" y="70">Review signal</text></g>
      <g class="orbit-core" transform="translate(328 266)">
        <circle class="core-pulse" r="94"/><circle r="74"/>
        <text y="-10">REVIEWED</text><text y="18">PUBLICATION</text><path d="m-16 42 13 13 28-31"/>
      </g>
    </svg>
    <figcaption><span>Evidence map</span> Every public claim must retain a visible path back to its source.</figcaption>
  </figure>`;

export const illustrativeSequence = `
  <figure class="sequence-visual" aria-labelledby="sequence-title">
    <figcaption id="sequence-title"><span>Illustrative sequence</span>A conceptual path across public records, not a real project or allegation.</figcaption>
    <div class="sequence-track" aria-hidden="true">
      <div class="sequence-item"><b>01</b><span>Appropriation</span><i></i></div>
      <div class="sequence-item"><b>02</b><span>Agency</span><i></i></div>
      <div class="sequence-item"><b>03</b><span>Procurement</span><i></i></div>
      <div class="sequence-item"><b>04</b><span>Implementation</span><i></i></div>
      <div class="sequence-item"><b>05</b><span>Audit</span></div>
    </div>
  </figure>`;

export const signalAnatomy = `
  <div class="signal-visual" aria-label="Anatomy of a transparent review signal">
    <div class="signal-head"><span class="signal-pulse" aria-hidden="true"></span><p>Review signal</p><strong>Question raised</strong></div>
    <dl>
      <div><dt>Rule</dt><dd>The exact, versioned condition that produced the signal.</dd></div>
      <div><dt>Inputs</dt><dd>The source-linked records used by the calculation.</dd></div>
      <div><dt>Limits</dt><dd>Known gaps and reasons the signal may be incomplete.</dd></div>
    </dl>
  </div>`;

export const gateVisual = `
  <div class="gate-visual" aria-label="Four requirements must pass before the public register opens">
    <div class="gate-status"><span></span><p>Register status</p><strong>Verification in progress</strong></div>
    <ul>
      <li><span>100+</span><p>reviewed linkage cases</p></li><li><span>≥95%</span><p>measured precision</p></li>
      <li><span>≥95%</span><p>reviewer agreement</p></li><li><span>0</span><p>critical reconciliation failures</p></li>
    </ul>
  </div>`;

export const methodDiagram = `
  <figure class="method-diagram" aria-label="Records pass through four evidence stages">
    <div><span>01</span><strong>Preserve</strong><small>Source and archive</small></div><i aria-hidden="true"></i>
    <div><span>02</span><strong>Normalize</strong><small>Schema and controls</small></div><i aria-hidden="true"></i>
    <div><span>03</span><strong>Link</strong><small>Identity and confidence</small></div><i aria-hidden="true"></i>
    <div><span>04</span><strong>Review</strong><small>Quarantine or publish</small></div>
  </figure>`;
