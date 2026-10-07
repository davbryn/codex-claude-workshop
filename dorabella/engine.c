/* Simulated annealing over symbol -> letter keys, in C so experiments can afford thousands
   of runs (every hypothesis is also run on decoys).  Built and loaded by engine.py.

   A key gives each cipher symbol a letter, or -1 for a null (a symbol that is skipped).
   The plaintext is key[seq[i]] for every position; a negative entry in seq is a break
   (no quadgram is scored across it, e.g. between the cipher's lines).  The score is the
   summed quadgram log-probability of the plaintext.

   fixed[s]  -2: free;  -1: always a null;  >= 0: always that letter.
   group[s]  symbols in the same group must take different letters when injective != 0
             (one group = ordinary one-to-one substitution; one group per line or per
             position class = a separate alphabet for each).
*/
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint64_t s; } Rng;

static inline uint64_t next64(Rng *r)
{   /* splitmix64 */
    uint64_t z = (r->s += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}
static inline double uniform(Rng *r) { return (next64(r) >> 11) * 0x1.0p-53; }
static inline int below(Rng *r, int n) { return (int)(uniform(r) * n); }

double score_key(const int *seq, int n, const int *key, const float *quad, int A, int *count)
{
    double s = 0;
    int run[4], m = 0, grams = 0;
    for (int i = 0; i < n; i++) {
        if (seq[i] < 0) { m = 0; continue; }
        int c = key[seq[i]];
        if (c < 0) continue;
        run[0] = run[1]; run[1] = run[2]; run[2] = run[3]; run[3] = c;
        if (++m >= 4) {
            s += quad[((run[0] * A + run[1]) * A + run[2]) * A + run[3]];
            grams++;
        }
    }
    if (count) *count = grams;
    return s;
}

/* Returns the best summed score; best_key receives its key.  run_best (may be NULL) gets
   each restart's best summed score. */
double anneal(const int *seq, int n, int S, const float *quad, int A,
              const int *fixed, const int *group, int injective,
              int restarts, int iters, double t0, double t1, uint64_t seed,
              int *best_key, double *run_best)
{
    Rng rng = { seed * 0x2545F4914F6CDD1DULL + 1 };
    int G = 1;
    for (int s = 0; s < S; s++) if (group[s] + 1 > G) G = group[s] + 1;
    int *key = malloc(S * sizeof(int)), *keep = malloc(S * sizeof(int));
    int *owner = malloc((size_t)G * A * sizeof(int));
    int *free_syms = malloc(S * sizeof(int)), n_free = 0;
    for (int s = 0; s < S; s++) if (fixed[s] == -2) free_syms[n_free++] = s;
    double best = -INFINITY;
    double ratio = iters > 1 ? pow(t1 / t0, 1.0 / (iters - 1)) : 1.0;

    for (int r = 0; r < restarts; r++) {
        /* random start: fixed symbols first, then free ones take random (unused) letters */
        for (int i = 0; i < G * A; i++) owner[i] = -1;
        for (int s = 0; s < S; s++) {
            key[s] = fixed[s] >= -1 ? fixed[s] : -1;
            if (key[s] >= 0) owner[group[s] * A + key[s]] = s;
        }
        for (int k = 0; k < n_free; k++) {
            int s = free_syms[k], c;
            if (injective) {
                int tries = 0;
                do { c = below(&rng, A); } while (owner[group[s] * A + c] >= 0 && ++tries < 10000);
                owner[group[s] * A + c] = s;
            } else c = below(&rng, A);
            key[s] = c;
        }
        double cur = score_key(seq, n, key, quad, A, NULL), top = cur;
        memcpy(keep, key, S * sizeof(int));
        double T = t0;

        for (int it = 0; it < iters && n_free; it++, T *= ratio) {
            int s = free_syms[below(&rng, n_free)], c = below(&rng, A), old = key[s];
            if (c == old) continue;
            int o = -1;
            if (injective) {
                o = owner[group[s] * A + c];
                if (o >= 0 && fixed[o] != -2) continue;   /* letter held by a fixed symbol */
                key[s] = c;
                if (o >= 0) key[o] = old;
            } else key[s] = c;
            double now = score_key(seq, n, key, quad, A, NULL);
            if (now >= cur || uniform(&rng) < exp((now - cur) / T)) {
                cur = now;
                if (injective) {
                    owner[group[s] * A + c] = s;
                    owner[group[s] * A + old] = o;
                }
                if (cur > top) { top = cur; memcpy(keep, key, S * sizeof(int)); }
            } else {
                key[s] = old;
                if (o >= 0) key[o] = c;
            }
        }
        if (run_best) run_best[r] = top;
        if (top > best) { best = top; memcpy(best_key, keep, S * sizeof(int)); }
    }
    free(key); free(keep); free(owner); free(free_syms);
    return best;
}
