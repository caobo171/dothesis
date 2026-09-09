# Canonical sources

**This file is the entire citation allowlist.** A DoThesis post may cite these
works and nothing else. Use the in-text string exactly as given in the first
column; the reader is going to paste it into a thesis that gets defended, so a
mangled year or a half-remembered title is worse than no citation at all.

If a claim needs a source that is not here, do not invent one. Describe the shape
of the thing without the number, or leave the claim out. Adding an entry to this
file is a deliberate act: the work must be real, well known in this market, and
checked. When unsure of a year or a title, leave it out.

The QA gate (`api/app/blog/content/qa.py`) holds the same list as
`(surname, year)` pairs and fails any post that cites something else. The two are
kept in sync by a test, so an entry added here without adding it there will show up
as a failing test, not as a bad post.

## In-text forms

Vietnamese theses use `(Tên, năm)` for one author, `(Tên và Tên, năm)` for two, and
`(Tên và cộng sự, năm)` for three or more. The English `et al.` form is accepted by
the gate as well, since both appear in real Vietnamese theses. Narrative form
(`Hair và cộng sự (2010) đề xuất ...`) is fine.

## The list

| In-text | Full reference | What it backs |
|---|---|---|
| `(Cronbach, 1951)` | Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. *Psychometrika*, 16(3), 297-334. | Cronbach's Alpha itself |
| `(Nunnally, 1978)` | Nunnally, J. C. (1978). *Psychometric Theory* (2nd ed.). McGraw-Hill. | Alpha from 0.7 up is acceptable |
| `(Nunnally và Bernstein, 1994)` | Nunnally, J. C., & Bernstein, I. H. (1994). *Psychometric Theory* (3rd ed.). McGraw-Hill. | Corrected item-total correlation from 0.3 up |
| `(Kaiser, 1960)` | Kaiser, H. F. (1960). The application of electronic computers to factor analysis. *Educational and Psychological Measurement*, 20(1), 141-151. | Eigenvalue above 1 as the extraction rule |
| `(Kaiser, 1974)` | Kaiser, H. F. (1974). An index of factorial simplicity. *Psychometrika*, 39(1), 31-36. | KMO from 0.5 up, and the KMO interpretation bands |
| `(Hair và cộng sự, 1998)` | Hair, J. F., Anderson, R. E., Tatham, R. L., & Black, W. C. (1998). *Multivariate Data Analysis* (5th ed.). Prentice-Hall. | The older factor-loading bands still cited in Vietnamese theses |
| `(Hair và cộng sự, 2010)` | Hair, J. F., Black, W. C., Babin, B. J., & Anderson, R. E. (2010). *Multivariate Data Analysis* (7th ed.). Pearson. | Factor loading from 0.5 up, total variance explained from 50% up, alpha down to 0.6 for an exploratory scale, 5 to 10 observations per item |
| `(Hair và cộng sự, 2011)` | Hair, J. F., Ringle, C. M., & Sarstedt, M. (2011). PLS-SEM: Indeed a silver bullet. *Journal of Marketing Theory and Practice*, 19(2), 139-152. | R² bands 0.75 / 0.50 / 0.25 in PLS-SEM |
| `(Hair và cộng sự, 2019)` | Hair, J. F., Risher, J. J., Sarstedt, M., & Ringle, C. M. (2019). When to use and how to report the results of PLS-SEM. *European Business Review*, 31(1), 2-24. | Reporting checklist for PLS-SEM, VIF below 5 |
| `(Hair và cộng sự, 2022)` | Hair, J. F., Hult, G. T. M., Ringle, C. M., & Sarstedt, M. (2022). *A Primer on Partial Least Squares Structural Equation Modeling (PLS-SEM)* (3rd ed.). Sage. | The current PLS-SEM procedure, 5,000 bootstrap subsamples, the two-stage assessment |
| `(Fornell và Larcker, 1981)` | Fornell, C., & Larcker, D. F. (1981). Evaluating structural equation models with unobservable variables and measurement error. *Journal of Marketing Research*, 18(1), 39-50. | CR from 0.7 up, AVE from 0.5 up, the Fornell-Larcker discriminant criterion |
| `(Henseler và cộng sự, 2015)` | Henseler, J., Ringle, C. M., & Sarstedt, M. (2015). A new criterion for assessing discriminant validity in variance-based structural equation modeling. *Journal of the Academy of Marketing Science*, 43(1), 115-135. | HTMT below 0.85 or 0.90 |
| `(Henseler và cộng sự, 2009)` | Henseler, J., Ringle, C. M., & Sinkovics, R. R. (2009). The use of partial least squares path modeling in international marketing. *Advances in International Marketing*, 20, 277-319. | Earlier PLS path-modelling reporting practice |
| `(Chin, 1998)` | Chin, W. W. (1998). The partial least squares approach to structural equation modeling. In G. A. Marcoulides (Ed.), *Modern Methods for Business Research* (pp. 295-336). Lawrence Erlbaum. | R² bands 0.67 / 0.33 / 0.19, outer loading from 0.7 up |
| `(Dijkstra và Henseler, 2015)` | Dijkstra, T. K., & Henseler, J. (2015). Consistent partial least squares path modeling. *MIS Quarterly*, 39(2), 297-316. | rho_A as a reliability measure in PLS |
| `(Stone, 1974)` | Stone, M. (1974). Cross-validatory choice and assessment of statistical predictions. *Journal of the Royal Statistical Society: Series B*, 36(2), 111-147. | Q² and the blindfolding logic |
| `(Bagozzi và Yi, 1988)` | Bagozzi, R. P., & Yi, Y. (1988). On the evaluation of structural equation models. *Journal of the Academy of Marketing Science*, 16(1), 74-94. | Composite reliability and convergent validity criteria |
| `(Anderson và Gerbing, 1988)` | Anderson, J. C., & Gerbing, D. W. (1988). Structural equation modeling in practice: A review and recommended two-step approach. *Psychological Bulletin*, 103(3), 411-423. | The two-step measurement-then-structural approach |
| `(Hu và Bentler, 1999)` | Hu, L., & Bentler, P. M. (1999). Cutoff criteria for fit indexes in covariance structure analysis. *Structural Equation Modeling*, 6(1), 1-55. | CFI and TLI from 0.90 up, RMSEA and SRMR at or below 0.08. CB-SEM only |
| `(Bollen, 1989)` | Bollen, K. A. (1989). *Structural Equations with Latent Variables*. Wiley. | Structural equation modelling fundamentals |
| `(Kline, 2015)` | Kline, R. B. (2015). *Principles and Practice of Structural Equation Modeling* (4th ed.). Guilford Press. | SEM practice and reporting |
| `(Byrne, 2010)` | Byrne, B. M. (2010). *Structural Equation Modeling with AMOS* (2nd ed.). Routledge. | AMOS procedure |
| `(Podsakoff và cộng sự, 2003)` | Podsakoff, P. M., MacKenzie, S. B., Lee, J.-Y., & Podsakoff, N. P. (2003). Common method biases in behavioral research. *Journal of Applied Psychology*, 88(5), 879-903. | Common method bias, Harman single-factor test |
| `(Baron và Kenny, 1986)` | Baron, R. M., & Kenny, D. A. (1986). The moderator-mediator variable distinction in social psychological research. *Journal of Personality and Social Psychology*, 51(6), 1173-1182. | The classic causal-steps mediation logic, and the mediator versus moderator distinction |
| `(Preacher và Hayes, 2008)` | Preacher, K. J., & Hayes, A. F. (2008). Asymptotic and resampling strategies for assessing and comparing indirect effects in multiple mediator models. *Behavior Research Methods*, 40(3), 879-891. | Bootstrapping the indirect effect, the confidence interval that must not contain zero |
| `(Hayes, 2018)` | Hayes, A. F. (2018). *Introduction to Mediation, Moderation, and Conditional Process Analysis* (2nd ed.). Guilford Press. | PROCESS macro models in SPSS |
| `(Cohen, 1988)` | Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences* (2nd ed.). Lawrence Erlbaum. | Effect sizes: f² at 0.02, 0.15, 0.35 |
| `(Tabachnick và Fidell, 2013)` | Tabachnick, B. G., & Fidell, L. S. (2013). *Using Multivariate Statistics* (6th ed.). Pearson. | Regression sample size n at or above 50 + 8m, assumption checking |
| `(Field, 2013)` | Field, A. (2013). *Discovering Statistics Using IBM SPSS Statistics* (4th ed.). Sage. | SPSS procedure, Durbin-Watson between 1 and 3, assumption diagnostics |
| `(Comrey và Lee, 1992)` | Comrey, A. L., & Lee, H. B. (1992). *A First Course in Factor Analysis* (2nd ed.). Lawrence Erlbaum. | Sample-size adequacy bands for factor analysis |
| `(Cochran, 1977)` | Cochran, W. G. (1977). *Sampling Techniques* (3rd ed.). Wiley. | Sample-size formula for a proportion |
| `(Yamane, 1967)` | Yamane, T. (1967). *Statistics: An Introductory Analysis* (2nd ed.). Harper and Row. | The finite-population sample-size formula used in most Vietnamese theses |
| `(Likert, 1932)` | Likert, R. (1932). A technique for the measurement of attitudes. *Archives of Psychology*, 140, 1-55. | The Likert scale itself |
| `(Davis, 1989)` | Davis, F. D. (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. *MIS Quarterly*, 13(3), 319-340. | TAM |
| `(Ajzen, 1991)` | Ajzen, I. (1991). The theory of planned behavior. *Organizational Behavior and Human Decision Processes*, 50(2), 179-211. | TPB |
| `(Venkatesh và cộng sự, 2003)` | Venkatesh, V., Morris, M. G., Davis, G. B., & Davis, F. D. (2003). User acceptance of information technology: Toward a unified view. *MIS Quarterly*, 27(3), 425-478. | UTAUT |
| `(Venkatesh và cộng sự, 2012)` | Venkatesh, V., Thong, J. Y. L., & Xu, X. (2012). Consumer acceptance and use of information technology: Extending UTAUT. *MIS Quarterly*, 36(1), 157-178. | UTAUT2 |
| `(Parasuraman và cộng sự, 1988)` | Parasuraman, A., Zeithaml, V. A., & Berry, L. L. (1988). SERVQUAL: A multiple-item scale for measuring consumer perceptions of service quality. *Journal of Retailing*, 64(1), 12-40. | SERVQUAL and its five dimensions |
| `(Nguyễn Đình Thọ, 2011)` | Nguyễn Đình Thọ (2011). *Phương pháp nghiên cứu khoa học trong kinh doanh*. NXB Lao động Xã hội. | The Vietnamese methods textbook most supervisors expect to see cited |
| `(Hoàng Trọng và Chu Nguyễn Mộng Ngọc, 2008)` | Hoàng Trọng và Chu Nguyễn Mộng Ngọc (2008). *Phân tích dữ liệu nghiên cứu với SPSS*. NXB Hồng Đức. | The Vietnamese SPSS textbook, cited for KMO, alpha and EFA thresholds in most theses |

## Thresholds you may state, and what backs each

Copy the source string with the number. Never state one without the other.

| Threshold | Cite |
|---|---|
| Cronbach's Alpha at 0.7 or above | `(Nunnally, 1978)` |
| Alpha from 0.6 acceptable for a new or exploratory scale | `(Hair và cộng sự, 2010)` |
| Corrected Item-Total Correlation at 0.3 or above | `(Nunnally và Bernstein, 1994)` |
| KMO at 0.5 or above, Bartlett significant below 0.05 | `(Kaiser, 1974)` |
| Eigenvalue above 1 | `(Kaiser, 1960)` |
| Total variance explained at 50% or above | `(Hair và cộng sự, 2010)` |
| Factor loading at 0.5 or above | `(Hair và cộng sự, 2010)` |
| Outer loading at 0.7 or above in PLS-SEM | `(Chin, 1998)` or `(Hair và cộng sự, 2022)` |
| CR at 0.7 or above, AVE at 0.5 or above | `(Fornell và Larcker, 1981)` |
| Square root of AVE above the inter-construct correlations | `(Fornell và Larcker, 1981)` |
| HTMT below 0.85, or below 0.90 for conceptually close constructs | `(Henseler và cộng sự, 2015)` |
| VIF below 5 | `(Hair và cộng sự, 2019)` |
| f² at 0.02 small, 0.15 medium, 0.35 large | `(Cohen, 1988)` |
| R² at 0.75 substantial, 0.50 moderate, 0.25 weak | `(Hair và cộng sự, 2011)` |
| Q² above 0 | `(Stone, 1974)` or `(Hair và cộng sự, 2022)` |
| 5,000 bootstrap subsamples | `(Hair và cộng sự, 2022)` |
| CFI and TLI at 0.90 or above, RMSEA and SRMR at 0.08 or below, CB-SEM only | `(Hu và Bentler, 1999)` |
| Indirect effect significant when the bootstrap CI excludes zero | `(Preacher và Hayes, 2008)` |
| Harman single factor below 50% of variance | `(Podsakoff và cộng sự, 2003)` |
| 5 to 10 observations per biến quan sát | `(Hair và cộng sự, 2010)` |
| Regression sample size at 50 + 8m or above | `(Tabachnick và Fidell, 2013)` |
| Durbin-Watson between 1 and 3 | `(Field, 2013)` |
| Sample size from the finite-population formula | `(Yamane, 1967)` |

Two reminders that catch people out. Fit indices from `(Hu và Bentler, 1999)` are
CB-SEM only and must never appear in a SmartPLS post. The Vietnamese textbooks,
`(Hoàng Trọng và Chu Nguyễn Mộng Ngọc, 2008)` and `(Nguyễn Đình Thọ, 2011)`, are the
citations a Vietnamese supervisor recognises fastest, so pair the international
source with the Vietnamese one where both apply.

## Kinh tế lượng

Thêm 2026-09-08, khi trục chủ đề có thêm dữ liệu bảng và chuỗi thời gian. Chỉ
bốn kinh điển, mỗi cái là chính bài báo mà phương pháp mang tên.

| Trích dẫn | Nguồn |
|---|---|
| `(Engle và Granger, 1987)` | Engle, R. F., & Granger, C. W. J. (1987). Co-integration and error correction: representation, estimation, and testing. *Econometrica*, 55(2), 251-276. |
| `(Granger, 1969)` | Granger, C. W. J. (1969). Investigating causal relations by econometric models and cross-spectral methods. *Econometrica*, 37(3), 424-438. |
| `(Dickey và Fuller, 1979)` | Dickey, D. A., & Fuller, W. A. (1979). Distribution of the estimators for autoregressive time series with a unit root. *Journal of the American Statistical Association*, 74(366), 427-431. |
| `(Hausman, 1978)` | Hausman, J. A. (1978). Specification tests in econometrics. *Econometrica*, 46(6), 1251-1271. |
