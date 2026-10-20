"""The extractor's vocabulary (docs/CODEMAP_DESIGN.md, blueprint 4.2): which call names mean which verb, what makes a
figure, what re-draws rows, what converts a type. Fixed tables; the map is only as good as they are, so a chain written
in a style they do not name is marked, never guessed (4.13)."""
import ast

KERNEL = {"df": "primary", "DS": "primary", "CTX": "context"}          # names the kernel provides
MODULES0 = {"pd", "np", "plt"}                                         # pre-imported in the kernel
DOCUMENT_RE = r"^D\d+$"                                                # D1, D2, ...: the documents attached to the thread

LOADS = {"read_csv", "read_parquet", "read_excel", "read_json", "read_table", "read_feather", "read_pickle"}
CTX_CALLS = {"frame": "context passages", "codes": "context codes", "grep": "context passages", "around": "context passages",
             "between": "context passages", "on": "context passages", "text": "context passages"}
CTX_FILE = {"context passages": "context_notes.csv", "context codes": "context_codes.csv"}
FILTER_M = {"dropna": "drop rows with missing values", "drop_duplicates": "drop duplicate rows", "query": "keep rows where",
            "nlargest": "keep the largest", "nsmallest": "keep the smallest", "head": "keep the first rows", "tail": "keep the last rows"}
COMBINE_M = {"merge", "join", "concat", "combine_first"}
RESHAPE_M = {"pivot_table": "pivot", "pivot": "pivot", "melt": "unpivot", "stack": "stack", "unstack": "unstack",
             "explode": "explode", "crosstab": "cross-tabulate"}
SUMMARISE_M = {"groupby": "group by", "resample": "resample by period", "rolling": "rolling window", "value_counts": "count values",
               "describe": "describe", "agg": "aggregate", "aggregate": "aggregate", "sum": "sum", "mean": "mean",
               "median": "median", "std": "standard deviation", "var": "variance", "count": "count", "size": "count rows",
               "nunique": "count distinct", "quantile": "quantile", "percentile": "percentile", "cumsum": "running total",
               "corr": "correlation matrix", "ewm": "exponential average", "crosstab": "cross-tabulate"}
DERIVE_M = {"to_datetime": "parse dates", "to_numeric": "make numeric", "astype": "change type", "assign": "add columns",
            "where": "conditional value", "fillna": "fill missing", "clip": "clip", "round": "round", "replace": "recode",
            "apply": "apply a function", "shift": "shift", "diff": "difference", "pct_change": "percent change",
            "rank": "rank", "normalize": "to day", "cut": "bin values", "qcut": "bin by quantile", "div": "divide"}
TESTS = {"spearmanr": "Spearman rank correlation", "pearsonr": "Pearson correlation", "kendalltau": "Kendall tau",
         "linregress": "linear regression", "ttest_ind": "two-sample t-test", "ttest_rel": "paired t-test",
         "ttest_1samp": "one-sample t-test", "mannwhitneyu": "Mann-Whitney U test", "wilcoxon": "Wilcoxon signed-rank test",
         "kruskal": "Kruskal-Wallis test", "chi2_contingency": "chi-square test", "fisher_exact": "Fisher exact test",
         "binomtest": "binomial test", "proportion_confint": "interval for a proportion", "theilslopes": "Theil-Sen slope",
         "polyfit": "polynomial fit", "corrcoef": "correlation", "ols": "OLS regression", "OLS": "OLS regression",
         "mixedlm": "mixed-effects model", "glm": "GLM", "logit": "logistic regression", "gls": "GLS regression",
         "shapiro": "normality test", "levene": "equal-variance test", "f_oneway": "one-way ANOVA",
         "bootstrap": "bootstrap", "norm": "normal distribution", "t": "t distribution", "sem": "standard error"}
RESAMPLE_HINTS = {"integers", "choice", "permutation"}
DRAW_PREFIX = ("go.", "px.", "plt.", "sns.", "make_subplots", "ff.")
DRAW_M = {"add_trace", "update_layout", "add_vline", "add_hline", "add_annotation", "update_xaxes", "update_yaxes", "plot",
          "scatter", "bar", "hist", "savefig", "show"}
# a name bound to a new figure (or its axes): later calls that draw on it change that figure, so its recipe holds what
# its traces, annotations and helper calls read (fig = go.Figure(); fig.add_trace(...); lines3d(fig, ...))
FIG_MAKERS = ("go.Figure", "go.FigureWidget", "make_subplots", "plotly.subplots.make_subplots", "sp.make_subplots",
              "plt.subplots", "plt.figure", "plt.gca", "plt.gcf", "plt.subplot", "px.", "ff.create_", "sns.")
FIG_PANDAS = {"plot", "hist", "boxplot"}                 # ax = df.plot(...): axes to draw on
FIG_KEEP = {"show", "savefig", "write_image", "write_html", "to_html", "to_json", "to_image", "to_dict", "to_plotly_json",
            "close"}
# words on a figure, not the data drawn: a number quoted in a title or an annotation keeps its own recipe
LABEL_KW = {"text", "title", "title_text", "name", "hovertext", "hovertemplate", "texttemplate", "annotation_text",
            "xaxis_title", "yaxis_title", "zaxis_title", "legend_title", "legend_title_text", "labels", "label", "customdata",
            "hoverinfo", "legendgroup", "xlabel", "ylabel", "text_auto", "subplot_titles", "column_titles", "row_titles"}
LABEL_M = {"set_title", "set_xlabel", "set_ylabel", "set_zlabel", "suptitle", "title", "xlabel", "ylabel", "legend",
           "set_xticklabels", "set_yticklabels"}
# a name re-bound to its own values under another type is the same value carried on, not a new one
CONVERT_F = {"np.asarray", "np.array", "np.asanyarray", "np.ascontiguousarray", "list", "tuple", "float", "int",
             "np.float64", "pd.Series", "pd.DataFrame", "pd.to_numeric", "copy.copy", "copy.deepcopy"}
CONVERT_M = {"astype", "copy", "to_numpy", "tolist", "to_list"}
MUTATORS = {"append", "extend", "update", "insert", "add", "pop", "remove", "setdefault", "sort", "clear"}
TIDY = {"parse dates", "to day", "make numeric", "change type", "fill missing", "round", "divide", "recode", "map values",
        "apply a function", "conditional value", "clip"}
# typed values the map evaluates without the data: dates, offsets and their arithmetic (objects.safe_value)
SAFE_CALLS = {"pd.Timestamp", "pd.Timedelta", "pd.to_datetime", "pd.DateOffset", "int", "float", "str", "round"}
RESAMPLE_PARAMS = ("B", "N_BOOT", "NBOOT", "N_RESAMPLES")   # a helper's numeric default under one of these names is a resample count

CMP = {ast.Gt: ">", ast.GtE: "≥", ast.Lt: "<", ast.LtE: "≤", ast.Eq: "=", ast.NotEq: "≠", ast.In: "in", ast.NotIn: "not in",
       ast.Is: "is", ast.IsNot: "is not"}
