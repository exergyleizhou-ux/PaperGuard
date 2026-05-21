# statcheck-R driver: load the same N=41 corpus PaperGuard B4 was
# benchmarked against, run statcheck (the original Nuijten et al. 2016
# implementation), and write per-claim results as JSON for the Python
# Cohen's kappa analyser.
#
# Usage:
#   "C:/Program Files/R/R-4.6.0/bin/Rscript.exe" \
#       scripts/crossval_statcheck_r.R \
#       scripts/crossval_statcheck_corpus.txt \
#       scripts/crossval_statcheck_r_results.json
#
# Input file is a plain-text dump of all corpus claims concatenated
# with sentence boundaries; statcheck() parses it directly.

lib_path <- "C:/Users/USER/R-libs"
.libPaths(c(lib_path, .libPaths()))
suppressPackageStartupMessages(library(statcheck))
suppressPackageStartupMessages(library(jsonlite))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  cat("usage: crossval_statcheck_r.R <corpus.txt> <out.json>\n", file = stderr())
  quit(status = 1)
}
input_path <- args[1]
output_path <- args[2]

text <- readLines(input_path, warn = FALSE)
text <- paste(text, collapse = " ")

cat(sprintf("Loaded %d characters\n", nchar(text)), file = stderr())

results <- statcheck(text)
if (is.null(results) || nrow(results) == 0) {
  cat("statcheck found zero claims — writing empty results\n", file = stderr())
  writeLines(toJSON(list(claims = list()), auto_unbox = TRUE),
             output_path)
  quit(status = 0)
}

cat(sprintf("statcheck flagged %d claims\n", nrow(results)), file = stderr())

# Convert to a clean JSON-friendly record per claim.
records <- list()
for (i in seq_len(nrow(results))) {
  row <- results[i, ]
  rec <- list(
    test_type      = as.character(row$test_type),
    df1            = if (is.na(row$df1)) NULL else as.numeric(row$df1),
    df2            = if (is.na(row$df2)) NULL else as.numeric(row$df2),
    test_value     = as.numeric(row$test_value),
    reported_comp  = as.character(row$p_comp),
    reported_p     = as.numeric(row$reported_p),
    computed_p     = as.numeric(row$computed_p),
    raw_text       = as.character(row$raw),
    error          = isTRUE(as.logical(row$error)),
    decision_error = isTRUE(as.logical(row$decision_error))
  )
  records[[length(records) + 1]] <- rec
}

writeLines(
  toJSON(list(claims = records), auto_unbox = TRUE, null = "null"),
  output_path
)
cat(sprintf("Wrote %s\n", output_path), file = stderr())
