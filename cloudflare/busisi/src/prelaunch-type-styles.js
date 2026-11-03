export const typeCss = `
html{font-size:100%;text-size-adjust:100%}
body{font-size:var(--text-md);line-height:1.6;background:#fff}
body:before{display:none;content:none}
.site-header{background:rgba(255,255,255,.98)}
p,li,dd{line-height:1.6}
h1,h2,h3,.hero h1,.page-intro h1,.data-intro h1,.dossier-header h1{font-family:var(--sans);font-weight:700;text-wrap:balance}
h1,.hero h1,.page-intro h1,.data-intro h1,.dossier-header h1,.not-found h1{font-size:var(--heading-lg);line-height:1.05;letter-spacing:-.025em}
h2,.preview-heading h2,.signal-catalog h2,.candidate-warning h2,.dossier-grid h2,.dossier-sources h2{font-size:var(--heading-md);line-height:1.12;letter-spacing:-.02em}
h3,.principle h3,.pipeline-group h3,.policy-item h3,.standard-panel h3,.preview-panels h3,.coverage-list h3{font-size:var(--heading-sm);line-height:1.3;letter-spacing:-.01em}
.hero .lede,.page-intro .lede,.data-intro .lede,.section-intro,.gate-copy>p:not(.kicker),.signal-layout>div>p:last-child,.candidate-warning p,.not-found>p{font-family:var(--sans);font-size:var(--text-lg);line-height:1.65}
.eyebrow,.kicker,.section-number,.sequence-visual figcaption span,.sequence-item b,.page-map span,.utility-inner,.hero-art-note,.preview-panels article>span,.preview-panels>a>span,.preview-panels small,.snapshot-card span,.dataset-stats p,.record-type,.signal-head p,.signal-head strong,.signal-visual dt,.signal-catalog article>span,.signal-catalog dt,.coverage-list article>span,.dossier-header aside span,.dossier-header aside small,.amount-comparison span,.amount-comparison small,.dossier-grid dt,.pipeline-group>span,.pipeline-group li:before,.policy-item span,.method-diagram span{font-size:var(--text-xs);letter-spacing:.08em}
.primary-nav a,.actions a,.text-link,.footer-nav a,.snapshot-card a,.explorer-tabs button,.explorer-controls label,.explorer-controls button,.explorer-actions button,.record-links a,.signal-catalog a,.dossier-sources a,.local-nav span,.local-nav a{font-size:var(--text-sm);letter-spacing:.05em}
.evidence-orbit figcaption,.sequence-visual figcaption,.gate-status p,.gate-visual li p,.footer-brand p,.footer-note,.snapshot-card p,.explorer-notice,.result-summary,.record-card p,.record-card .record-amount span,.record-meta span,.signal-catalog dd,.coverage-list p,.dossier-breadcrumbs,.dossier-grid aside p:last-child,.method-diagram small,.pipeline-group small,.policy-item p{font-size:var(--text-sm)}
.orbit-node text,.orbit-node .node-label,.orbit-core text{font-size:13px}
.explorer-controls input,.explorer-controls select{font-size:var(--text-md);line-height:1.5}
.record-card h2{font-size:1.125rem;line-height:1.4}
.record-card .record-amount strong,.snapshot-card strong,.coverage-list h3,.amount-comparison strong{font-family:var(--sans);font-weight:700}
.wordmark,.wordmark span{font-size:1rem;letter-spacing:.08em}
.page-map a,.sequence-item span,.method-diagram strong,.pipeline-group strong,.gate-status strong,.dossier-header aside strong,.footer-brand strong{font-family:var(--sans)}
.hero-copy,.page-map,.system-panel,.gate-visual,.local-nav,.pipeline-groups,.policy-item,.standard-panel,.preview-panels,.preview-panels>a,.dataset-stats,.explorer-shell,.signal-catalog article,.coverage-list,.amount-comparison,.dossier-grid aside{background:#fff}
.explorer-notice,.dossier-warning{background:var(--soft)}
.record-card:hover,.preview-panels>a:hover{background:var(--soft)}
a,button,input,select{font-family:var(--sans)}
button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--rust);outline-offset:3px}
@media(max-width:720px){
  .primary-nav a,.utility-inner{font-size:var(--text-xs)}
  .hero h1,.page-intro h1,.data-intro h1,.dossier-header h1{font-size:clamp(2.5rem,11vw,3.25rem);line-height:1.08}
  h2,.preview-heading h2,.signal-catalog h2,.candidate-warning h2,.dossier-grid h2,.dossier-sources h2{font-size:clamp(1.875rem,8vw,2.5rem)}
  .hero .lede,.page-intro .lede,.data-intro .lede,.section-intro{font-size:var(--text-md)}
}
@media(prefers-contrast:more){
  :root{--line:#65736e;--muted:#263c35;--rust:#7f2015}
  a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline-width:4px}
}
`;
