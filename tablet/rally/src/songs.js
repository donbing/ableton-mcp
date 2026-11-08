// Tunes for Rally's Notes mode: the ball lands on one key at a time, the left hand on bass roots and the right on
// a melody note that sits in the same chord. Each side steps through its own list on each landing there; the
// chord for a landing is chords[step % chords.length], so the bass and the melody of one step share a chord.
// Pitches are MIDI notes (60 = C3 in Live's names, as the page shows them).

export const SONGS = {
  vamp: {
    name: 'Am – F – C – G',
    names: ['Am', 'F', 'C', 'G'],
    chords: [[57, 60, 64], [53, 57, 60], [55, 60, 64], [55, 59, 62]], // soft triads around middle C
    low: [45, 41, 36, 43],                                         // A1 F1 C1 G1
    high: [76, 77, 76, 74, 72, 69, 67, 71],                        // E4 F4 E4 D4, C4 A3 G3 B3
  },
};

export function chordFor(song, step) {
  const i = step % song.chords.length;
  return { name: song.names[i], notes: song.chords[i] };
}
