prompt_extract = """You will be given a question and a table.
You must indicate the indices of the rows and indices of the columns that could be relevant to answer the question. You must not try to answer the question, you must only retrieve the relevant rows. You must use the values in the "index" column to refer to the relevant rows. For the column indices, write the number (from left to right starting from 0), not the column name.
First reason step-by-step. Then, write "Final answer: " followed exclusively by a Python dictionary:
{{
    "rows": [row_index1,...,row_indexn],
    "columns": [column_index1,...,column_indexn],
}}
The column indices must start from 0.
Ensure that the final answer is in the expected form. Do not write anything else after "Final answer:". Do not use Markdown syntax.

Question: {question}
Table: {table}

Let's think step-by-step. """

prompt_normalization = """Given multiple tables and a question, decide the unit of measure to use for the final answer.
Then, align the table values by converting the needed values to a unique unit of measurement.
If the question specifies the unit of measurement, convert the values to that unit of measurement. Otherwise, you must decide the unit of measurement and convert the values.
You must not rewrite the tables. You must only eventually write a list of rules/formulas indicating how to perform the needed transformations.
First reason step-by-step. Then write "Final answer: " followed exclusively by the list of rules/formulas.

Do not try to answer the question, but focus only on the given task. Ensure that the final answer is in the expected form. Do not write anything else after "Final answer:". Do not use Markdown syntax.

Question: {question}
Tables: {tables}

Let's think step-by-step. """

prompt_fallback_python = """
Consider the following question and content. First reason step-by-step, then provide the answer.

Question. {question}
Content: {content}

Let's think step-by-step. """

prompt_total = """
You must create the python code capable of answering the following question given the provided tables. First write your reasoning. Then, in the end, write "Final answer:" followed by the python code and nothing else. The Python code must be runnable "as it is", so make sure to include the relevant imports. At the end of the python function, print() the result.
If the question is boolean, the output must be exclusively a 'yes' or 'no' answer. If the question asks for a list of values, you must answer with a list of values separated with a comma. Write the numerical values with exactly 2 decimal values.
Ensure that the final answer is in the expected form. Do not write anything else after "Final answer:". Do not use Markdown syntax.

Question: {question}
Tables: {paragraph}

Let's think step-by-step.
"""