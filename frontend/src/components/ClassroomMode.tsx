export function ClassroomMode() {
  return (
    <section className="panel" aria-label="Classroom mode">
      <h2>Classroom: how Pluto was found</h2>
      <ol>
        <li>Two photographs of the same stars, taken on different nights.</li>
        <li>Blink them: almost every point of light stays put.</li>
        <li>One point hops — that moving speck was Pluto.</li>
        <li>SkyFlip does the same idea with SPHEREx infrared visits.</li>
      </ol>
      <p className="hint">
        Try WISE 0855 next: a nearby brown dwarf whose motion is large enough to see even with coarse
        6.15″ pixels.
      </p>
    </section>
  );
}
