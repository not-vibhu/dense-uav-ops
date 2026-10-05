# Campaign frontier-02

144 runs. Outcome digest `d4db35da9275c28d`; simulation core `bf06c50408cbe430`.

Attributable UAS events involve at least one controlled aircraft and no manned aircraft and occur in flight, i.e. not within one report interval of either aircraft entering (entry-phase events are listed separately in summary.json); rates are per controlled flight-hour in the measurement window, and per 1000 controlled operations completed in that window. Delay is completion minus (request + nominal traversal time), with unfinished operations counted at the end of the drain window (a lower bound). Intervals in summary.json assume independent events and are optimistic; per-run values are listed there too.

| arm | demand.uas_per_hour | fleet.noncompliant_acceleration_mps2 | fleet.noncompliant_fraction | runs | mean occupancy | throughput/h | completion | mean delay s (lower bound) | fallback | attributable UAS LoS/h (events) | per 1000 ops | contacts (events) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 1440 | 1.5 | 0.1 | 3 | 18.3 | 1365 | 1.00 | -0.3 | — | 12.96 (43) | 172.7 | 4 |
| none | 1440 | 3.0 | 0.1 | 3 | 18.3 | 1365 | 1.00 | -0.3 | — | 13.57 (45) | 180.7 | 5 |
| none | 1440 | 1.5 | 0.3 | 3 | 18.3 | 1365 | 1.00 | -0.3 | — | 14.59 (39) | 193.1 | 3 |
| none | 1440 | 3.0 | 0.3 | 3 | 18.3 | 1365 | 1.00 | -0.3 | — | 16.09 (43) | 212.9 | 5 |
| none | 2880 | 1.5 | 0.1 | 3 | 39.3 | 2870 | 1.00 | -0.1 | — | 27.19 (195) | 370.7 | 30 |
| none | 2880 | 3.0 | 0.1 | 3 | 39.3 | 2870 | 1.00 | -0.1 | — | 27.46 (197) | 374.5 | 29 |
| none | 2880 | 1.5 | 0.3 | 3 | 39.3 | 2875 | 1.00 | -0.1 | — | 31.38 (178) | 428.9 | 31 |
| none | 2880 | 3.0 | 0.3 | 3 | 39.3 | 2865 | 1.00 | -0.1 | — | 30.68 (174) | 419.3 | 28 |
| predictive-A0 | 1440 | 1.5 | 0.1 | 3 | 18.4 | 1365 | 1.00 | -0.0 | 0.000 | 0.00 (0) | 0.0 | 0 |
| predictive-A0 | 1440 | 3.0 | 0.1 | 3 | 18.4 | 1365 | 1.00 | -0.0 | 0.000 | 0.00 (0) | 0.0 | 0 |
| predictive-A0 | 1440 | 1.5 | 0.3 | 3 | 18.4 | 1365 | 1.00 | 0.0 | 0.000 | 0.00 (0) | 0.0 | 0 |
| predictive-A0 | 1440 | 3.0 | 0.3 | 3 | 18.4 | 1360 | 1.00 | 0.1 | 0.001 | 0.00 (0) | 0.0 | 0 |
| predictive-A0 | 2880 | 1.5 | 0.1 | 3 | 39.5 | 2880 | 1.00 | 0.2 | 0.001 | 0.00 (0) | 0.0 | 0 |
| predictive-A0 | 2880 | 3.0 | 0.1 | 3 | 39.5 | 2880 | 1.00 | 0.2 | 0.001 | 0.00 (0) | 0.0 | 0 |
| predictive-A0 | 2880 | 1.5 | 0.3 | 3 | 39.6 | 2895 | 1.00 | 0.3 | 0.001 | 0.35 (2) | 4.8 | 0 |
| predictive-A0 | 2880 | 3.0 | 0.3 | 3 | 39.6 | 2885 | 1.00 | 0.3 | 0.001 | 0.17 (1) | 2.4 | 0 |
| predictive-A1 | 1440 | 1.5 | 0.1 | 3 | 18.5 | 1360 | 1.00 | 0.4 | 0.001 | 0.00 (0) | 0.0 | 0 |
| predictive-A1 | 1440 | 3.0 | 0.1 | 3 | 18.5 | 1365 | 1.00 | 0.4 | 0.001 | 0.00 (0) | 0.0 | 0 |
| predictive-A1 | 1440 | 1.5 | 0.3 | 3 | 18.5 | 1365 | 1.00 | 0.4 | 0.001 | 0.00 (0) | 0.0 | 0 |
| predictive-A1 | 1440 | 3.0 | 0.3 | 3 | 18.5 | 1360 | 1.00 | 0.6 | 0.001 | 0.37 (1) | 5.0 | 0 |
| predictive-A1 | 2880 | 1.5 | 0.1 | 3 | 40.0 | 2870 | 1.00 | 0.9 | 0.003 | 0.00 (0) | 0.0 | 0 |
| predictive-A1 | 2880 | 3.0 | 0.1 | 3 | 40.0 | 2875 | 1.00 | 0.9 | 0.002 | 0.00 (0) | 0.0 | 0 |
| predictive-A1 | 2880 | 1.5 | 0.3 | 3 | 40.1 | 2885 | 1.00 | 1.2 | 0.004 | 0.00 (0) | 0.0 | 0 |
| predictive-A1 | 2880 | 3.0 | 0.3 | 3 | 40.1 | 2885 | 1.00 | 1.1 | 0.004 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 1440 | 1.5 | 0.1 | 3 | 18.8 | 1370 | 1.00 | 1.0 | 0.004 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 1440 | 3.0 | 0.1 | 3 | 18.7 | 1370 | 1.00 | 0.9 | 0.004 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 1440 | 1.5 | 0.3 | 3 | 18.8 | 1370 | 1.00 | 1.4 | 0.004 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 1440 | 3.0 | 0.3 | 3 | 18.8 | 1365 | 1.00 | 1.3 | 0.005 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 2880 | 1.5 | 0.1 | 3 | 41.2 | 2865 | 1.00 | 2.6 | 0.013 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 2880 | 3.0 | 0.1 | 3 | 41.2 | 2860 | 1.00 | 2.8 | 0.014 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 2880 | 1.5 | 0.3 | 3 | 41.2 | 2865 | 1.00 | 3.3 | 0.016 | 0.00 (0) | 0.0 | 0 |
| predictive-A2 | 2880 | 3.0 | 0.3 | 3 | 41.4 | 2870 | 1.00 | 3.6 | 0.018 | 0.00 (0) | 0.0 | 0 |
| predictive-A4 | 1440 | 1.5 | 0.1 | 3 | 20.2 | 1355 | 1.00 | 4.5 | 0.042 | 0.00 (0) | 0.0 | 0 |
| predictive-A4 | 1440 | 3.0 | 0.1 | 3 | 19.8 | 1355 | 1.00 | 3.9 | 0.040 | 0.00 (0) | 0.0 | 0 |
| predictive-A4 | 1440 | 1.5 | 0.3 | 3 | 20.1 | 1355 | 1.00 | 5.8 | 0.047 | 0.00 (0) | 0.0 | 0 |
| predictive-A4 | 1440 | 3.0 | 0.3 | 3 | 20.0 | 1340 | 1.00 | 5.5 | 0.048 | 0.00 (0) | 0.0 | 0 |
| predictive-A4 | 2880 | 1.5 | 0.1 | 3 | 48.9 | 2665 | 1.00 | 15.8 | 0.125 | 0.33 (3) | 6.2 | 0 |
| predictive-A4 | 2880 | 3.0 | 0.1 | 3 | 49.3 | 2685 | 1.00 | 15.2 | 0.125 | 0.00 (0) | 0.0 | 0 |
| predictive-A4 | 2880 | 1.5 | 0.3 | 3 | 48.4 | 2710 | 1.00 | 16.7 | 0.133 | 0.13 (1) | 2.6 | 0 |
| predictive-A4 | 2880 | 3.0 | 0.3 | 3 | 48.4 | 2700 | 1.00 | 16.7 | 0.140 | 0.53 (4) | 10.5 | 0 |
| daidalus | 1440 | 1.5 | 0.1 | 3 | 18.4 | 1365 | 1.00 | 0.1 | — | 0.60 (2) | 8.0 | 0 |
| daidalus | 1440 | 3.0 | 0.1 | 3 | 18.4 | 1365 | 1.00 | 0.0 | — | 0.60 (2) | 8.0 | 0 |
| daidalus | 1440 | 1.5 | 0.3 | 3 | 18.4 | 1365 | 1.00 | 0.1 | — | 1.11 (3) | 14.9 | 0 |
| daidalus | 1440 | 3.0 | 0.3 | 3 | 18.5 | 1365 | 1.00 | 0.2 | — | 0.74 (2) | 9.9 | 0 |
| daidalus | 2880 | 1.5 | 0.1 | 3 | 39.9 | 2880 | 1.00 | 0.9 | — | 0.14 (1) | 1.9 | 0 |
| daidalus | 2880 | 3.0 | 0.1 | 3 | 39.9 | 2885 | 1.00 | 0.8 | — | 0.82 (6) | 11.3 | 0 |
| daidalus | 2880 | 1.5 | 0.3 | 3 | 39.9 | 2890 | 1.00 | 0.9 | — | 1.21 (7) | 16.7 | 0 |
| daidalus | 2880 | 3.0 | 0.3 | 3 | 40.0 | 2885 | 1.00 | 1.2 | — | 1.55 (9) | 21.5 | 1 |

No cell is an operational capacity or safety qualification. See docs/research-question.md for definitions.
