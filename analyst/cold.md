You are given a task as an analyst will be given it: QUESTION, the BRIEF it comes with, DATA where data is loaded,
and above them the earlier analyses it follows, where it follows any. You have nothing else: not the conversation
the question came out of, and no other earlier work.

Find what in QUESTION points to something you were not given: an earlier analysis, figure or version that is not
among those above, whether it is named by its day or as "the last one"; "as before" or "the usual one" where
nothing you were given says which; something said or agreed somewhere else. A day, a name or a value that the
data can settle is no such pointer. Do not carry out the task, and do not judge it.

Reply with one JSON object and nothing else:

{"cannot_place": ["<words of QUESTION, copied exactly>"]}

Three at most, each the fewest words that hold the pointer. An empty list where QUESTION can be worked from what
you were given.
