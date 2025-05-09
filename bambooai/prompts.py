# prompts.py

###########################################
### DEFAULTY EXAMPLES #####################
###########################################

default_example_output_df = """
Example Task 1:

Calculate the average pace for each 100-meter segment of the most recent run. Plot the results on a bar chart, highlighting the fastest segment.

Example Output 1:

```python
import pandas as pd
import plotly.graph_objects as go
import numpy as np

def computeDataframeIndex(df, order_by='Datetime', ascending=False):
    # Ensure Datetime is in datetime format
    if df['Datetime'].dtype == 'object':
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')

    # Define aggregation functions
    agg_functions = {
        'ActivityType': 'first',
        'Datetime': 'min',
        'Distance': lambda x: np.abs(x.max() - x.min()),
        'Latitude': 'first',
        'Longitude': 'first',
        'Elevation': 'mean',
        'Speed': 'mean',
        'Heartrate': 'mean',
        'Cadence': 'mean',
        'Power': 'mean',
        'AirTemperature': 'mean',
        'Gradient': 'mean',
        'LapID': 'max',
        'Calories': 'sum'
    }

    # Compute statistics for each activity
    activity_stats = df.groupby('ActivityID').agg(agg_functions).reset_index()

    # Calculate duration
    activity_stats['Duration'] = df.groupby('ActivityID')['Datetime'].apply(
        lambda x: (x.max() - x.min()).total_seconds()
    ).values

    # Rename columns
    new_columns = [
        'ActivityID', 'ActivityType', 'Datetime', 'Distance', 'StartLatitude',
        'StartLongitude', 'AvgElevation', 'AvgSpeed', 'AvgHeartrate', 'AvgCadence',
        'AvgPower', 'AvgAirTemperature', 'AvgGradient', 'NumberOfLaps', 'Calories', 'Duration'
    ]
    activity_stats.columns = new_columns

    # Round numeric columns to 3 decimal places
    numeric_cols = activity_stats.select_dtypes(include=[np.number]).columns
    activity_stats[numeric_cols] = activity_stats[numeric_cols].round(3)

    # Ensure NumberOfLaps is an integer
    activity_stats['NumberOfLaps'] = activity_stats['NumberOfLaps'].fillna(0).astype(int)

    # Sort the DataFrame based on the order_by parameter and ascending/descending option
    return activity_stats.sort_values(by=order_by, ascending=ascending)

# Define the calculatePaceFunction
def calculatePaceFunction(df, speed_col, activity_type_col):
    df = df[(df[speed_col] > 0) & (df[activity_type_col].str.lower() == 'run')].copy()
    df['Pace'] = 1000 / (df[speed_col] * 60)  # min/km for runs
    return df[df['Pace'].notna() & (df['Pace'] > 0)]

# Define determineSegments function for segmentation
def determineSegments(df, segment_type='distance', segment_distance=1000, segment_duration=1200):
    df = df.sort_values(by=['ActivityID', 'Datetime'])
    
    if segment_type == 'distance':
        def process_distance_group(group):
            total_distance = group['Distance'].max()
            complete_segments = int(total_distance // segment_distance)
            group['SegmentID'] = (group['Distance'] // segment_distance).astype(int)
            group.loc[group['SegmentID'] >= complete_segments, 'SegmentID'] = np.nan
            return group
        
        df = df.groupby('ActivityID', group_keys=False).apply(process_distance_group)
    
    return df
  
# The dataframe 'df' is already defined and populated with necessary data

# Step 1: Activity Indexation
activities_summary = computeDataframeIndex(df, order_by='Datetime', ascending=False)
most_recent_run = activities_summary[activities_summary['ActivityType'] == 'Run'].iloc[0]

# Get the ActivityID of the most recent run
activity_id = most_recent_run['ActivityID']

# Step 2: Detailed Run Data Retrieval
recent_run = df[df['ActivityID'].isin([activity_id])]

# Step 3: Pace Calculation
recent_run = calculatePaceFunction(recent_run, 'Speed', 'ActivityType')

# Step 4: Segmentation
segmented_run = determineSegments(recent_run, segment_type='distance', segment_distance=100)

# Step 5: Pace Aggregation
segment_pace = segmented_run.groupby('SegmentID')['Pace'].mean().reset_index()

# Identify the fastest segment (lowest pace)
fastest_segment = segment_pace.loc[segment_pace['Pace'].idxmin()]

# Create the Plotly visualization
fig = go.Figure()

# Add bar chart
fig.add_trace(go.Bar(
    x=segment_pace['SegmentID'],
    y=segment_pace['Pace'],
    marker_color=['red' if i == fastest_segment['SegmentID'] else 'skyblue' 
                 for i in segment_pace['SegmentID']],
    name='Pace'
))

# Update layout
fig.update_layout(
    title=f'Average Pace per 100m Segment (ActivityID: {{activity_id}})',
    xaxis_title='Segment Number',
    yaxis_title='Pace (min/km)',
    showlegend=False,
    template='plotly_white',
    annotations=[
        dict(
            x=fastest_segment['SegmentID'],
            y=fastest_segment['Pace'],
            text=f"Fastest: {fastest_segment['Pace']:.2f} min/km",
            showarrow=True,
            arrowhead=1,
            yshift=10
        )
    ]
    dragmode='pan',
    hovermode='closest',
    autosize=True
)

# Show the plot
fig.show()

# Output statistics
print(f"Activity ID: {{activity_id}}")
print(f"Fastest segment: Segment {fastest_segment['SegmentID']} with pace {fastest_segment['Pace']:.2f} min/km")
print(f"Slowest segment: Segment {segment_pace['SegmentID'].iloc[-1]} with pace {segment_pace['Pace'].max():.2f} min/km")
print(f"Average pace across all segments: {segment_pace['Pace'].mean():.2f} min/km")
```

Example Task 2:

Count the number of runs per month in 2021

Example Output 2:

```python
import pandas as pd
import plotly.graph_objects as go
import numpy as np

def computeDataframeIndex(df, order_by='Datetime', ascending=False):
    # Ensure Datetime is in datetime format
    if df['Datetime'].dtype == 'object':
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')

    # Define aggregation functions
    agg_functions = {
        'ActivityType': 'first',
        'Datetime': 'min',
        'Distance': lambda x: np.abs(x.max() - x.min()),
        'Latitude': 'first',
        'Longitude': 'first',
        'Elevation': 'mean',
        'Speed': 'mean',
        'Heartrate': 'mean',
        'Cadence': 'mean',
        'Power': 'mean',
        'AirTemperature': 'mean',
        'Gradient': 'mean',
        'LapID': 'max',
        'Calories': 'sum'
    }

    # Compute statistics for each activity
    activity_stats = df.groupby('ActivityID').agg(agg_functions).reset_index()

    # Calculate duration
    activity_stats['Duration'] = df.groupby('ActivityID')['Datetime'].apply(
        lambda x: (x.max() - x.min()).total_seconds()
    ).values

    # Rename columns
    new_columns = [
        'ActivityID', 'ActivityType', 'Datetime', 'Distance', 'StartLatitude',
        'StartLongitude', 'AvgElevation', 'AvgSpeed', 'AvgHeartrate', 'AvgCadence',
        'AvgPower', 'AvgAirTemperature', 'AvgGradient', 'NumberOfLaps', 'Calories', 'Duration'
    ]
    activity_stats.columns = new_columns

    # Round numeric columns to 3 decimal places
    numeric_cols = activity_stats.select_dtypes(include=[np.number]).columns
    activity_stats[numeric_cols] = activity_stats[numeric_cols].round(3)

    # Ensure NumberOfLaps is an integer
    activity_stats['NumberOfLaps'] = activity_stats['NumberOfLaps'].fillna(0).astype(int)

    # Sort the DataFrame based on the order_by parameter and ascending/descending option
    return activity_stats.sort_values(by=order_by, ascending=ascending)

# Step 1: Activity Indexation
activities_summary = computeDataframeIndex(df, order_by='Datetime', ascending=True)

# Step 2: 2021 Run Data Filtering
runs_2021 = activities_summary[
    (activities_summary['Datetime'].dt.year == 2021) &
    (activities_summary['ActivityType'] == 'Run')
]

# Step 3: Monthly Aggregation
monthly_runs = runs_2021.groupby(runs_2021['Datetime'].dt.to_period('M')).size().reset_index(name='Count')
monthly_runs['Month'] = monthly_runs['Datetime'].dt.strftime('%B')

# Find the month with most runs
max_runs_month = monthly_runs.loc[monthly_runs['Count'].idxmax()]

# Create the Plotly visualization
fig = go.Figure()

# Add bar chart
fig.add_trace(go.Bar(
    x=monthly_runs['Month'],
    y=monthly_runs['Count'],
    marker_color=['red' if month == max_runs_month['Month'] else 'skyblue' 
                 for month in monthly_runs['Month']],
    text=monthly_runs['Count'],  # Add text labels
    textposition='outside',  # Position labels outside of bars
))

# Update layout
fig.update_layout(
    title='Number of Runs per Month in 2021',
    xaxis_title='Month',
    yaxis_title='Number of Runs',
    template='plotly_white',
    showlegend=False,
    xaxis=dict(
        tickangle=45,  # Rotate x-axis labels
        tickmode='array',
        ticktext=monthly_runs['Month'],
        tickvals=monthly_runs['Month']
    ),
    # Add some padding to ensure labels are visible
    dragmode='pan',
    hovermode='closest',
    autosize=True
)

# Show the plot
fig.show()

# Output
print("Monthly Run Counts in 2021:")
print(monthly_runs[['Month', 'Count']])
print(f"\nTotal number of runs in 2021: {monthly_runs['Count'].sum()}")
print(f"Month with highest number of runs: {max_runs_month['Month']} ({max_runs_month['Count']} runs)")
```
"""
default_example_output_gen = """
```python
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# Data Retrieval
def fetch_stock_data(symbol, start_date, end_date):
    try:
        stock = yf.Ticker(symbol)
        df = stock.history(start=start_date, end=end_date)
        return df
    except Exception as e:
        print(f"Error fetching data")
        return None

# Define parameters
symbol = "AAPL"
start_date = "2020-01-01"
end_date = "2021-12-31"

# Fetch data
df = fetch_stock_data(symbol, start_date, end_date)

if df is not None:
    # Data Analysis
    df['Daily_Return'] = df['Close'].pct_change()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA50'] = df['Close'].rolling(window=50).mean()
    
    stats = {
        'Mean': df['Close'].mean(),
        'Median': df['Close'].median(),
        'Std Dev': df['Close'].std(),
        'Max': df['Close'].max(),
        'Min': df['Close'].min(),
    }

    # Create Plotly figure
    fig = go.Figure()

    # Add Close Price
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df['Close'],
            name='Close Price',
            line=dict(color='blue'),
        )
    )

    # Add 20-day Moving Average
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df['MA20'],
            name='20-day MA',
            line=dict(color='orange', dash='dash'),
        )
    )

    # Add 50-day Moving Average
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df['MA50'],
            name='50-day MA',
            line=dict(color='red', dash='dash'),
        )
    )

    # Update layout
    fig.update_layout(
        title=f'Stock Price Trend for {{symbol}}',
        xaxis_title='Date',
        yaxis_title='Price ($)',
        template='plotly_white',
        hovermode='x unified',
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01
        ),
        dragmode='pan',
        hovermode='closest',
        autosize=True
    )

    # Add range slider
    fig.update_xaxes(rangeslider_visible=True)

    # Show the plot
    fig.show()

    # Output
    print(f"\nStock Analysis Summary")
    print("\nKey Insights:")
    print(f"1. Highest price: ${df['Close'].max():.2f} on {df['Close'].idxmax().strftime('%Y-%m-%d')}")
    print(f"2. Lowest price: ${df['Close'].min():.2f} on {df['Close'].idxmin().strftime('%Y-%m-%d')}")
    print(f"3. Average daily return: {df['Daily_Return'].mean()*100:.2f}%")
else:
    print("Failed to retrieve stock data. Please check your inputs and try again.")
```
"""
default_example_plan_df = """
Example Task:

Calculate the average pace for each 100-meter segment of the most recent run. Plot the results on a bar chart, highlighting the fastest segment.

Example Output:

```yaml
problem_reflection:
  goal: "Calculate average pace for each 100 meter segment of the most recent Run and plot results"
  key_inputs: ["ActivityID", "ActivityType", "SegmentID", "Datetime", "Distance", "Speed"]
  main_output: "Bar chart of average pace per segment, highlighting the fastest segment"
  constraints: "Focus on the most recent Run activity"

dataset_comprehension:
  structure: 
    - "Hierarchical timeseries data with nested structure:"
    - "Dataframe"
    - "  └─ Activity (grouped by ActivityID)"
    - "      └─ Segment (ComputedSegment of 100 meters)"
    - "          └─ Measurement (grouped by Datetime)"
  key_variables:
    - "ActivityID: Unique identifier for each activity"
    - "ActivityType: Type of activity (e.g., Run)"
    - "SegmentID: Unique identifier for each 100m segment"
    - "Datetime: Timestamp of each measurement (ISO 8601 format)"
    - "Distance: Cumulative distance in meters"
    - "Speed: Speed in meters per second"
  relationships:
    - "Each Activity contains multiple ComputedSegments"
    - "Each ComputedSegment contains multiple Measurements"
  aggregations:
    - "segment_duration: Duration of each 100m Segment"
    - "average_pace: Average Pace for each Segment"
  potential_issues: 
    - "Pace needs to be calculated from Speed"
    - "Ensuring exact 100m segments may require interpolation"

data_operations:
  - "Generate DataframeIndex using computeDataframeIndex function"
  - "Filter the most recent Run activity from the DataframeIndex"
  - "Retrieve detailed data for the most recent Run"
  - "Create 100 meter ComputedSegments using determineSegments function"
  - "Calculate Pace for each measurement"
  - "Aggregate average pace for each segment"

analysis_steps:
  - step: "Activity Indexation"
    purpose: "Generate summary statistics and identify the most recent Run"
    actions: 
      - "Use computeDataframeIndex function to generate index of all activities"
      - "Filter for Run activities and identify the most recent"
    expected_outcome: "DataframeIndex with the most recent Run identified"

  - step: "Detailed Run Data Retrieval"
    purpose: "Get detailed data for the most recent Run"
    actions: ["Filter original DataFrame for the ActivityID of the most recent Run"]
    expected_outcome: "DataFrame with detailed measurements for the most recent Run"

  - step: "Segmentation"
    purpose: "Create 100 meter ComputedSegments"
    actions: ["Use determineSegments function to create segments"]
    expected_outcome: "DataFrame with ComputedSegments for the Run"

  - step: "Pace Calculation"
    purpose: "Calculate Pace for each measurement"
    actions: ["Use calculatePaceFunction to calculate running Pace (minutes per kilometer)"]
    expected_outcome: "DataFrame with additional Pace column"

  - step: "Pace Aggregation"
    purpose: "Calculate average pace for each segment"
    actions: ["Group by SegmentID and calculate mean Pace"]
    formula: "Average Pace = Σ(Pace) / Number of Measurements"
    expected_outcome: "DataFrame with average pace per segment"

visualization:
  - plot1:
      type: "Bar plot"
      title: "Average Pace per 100m Segment"
      x_axis: "Segment number"
      y_axis: "Average pace (min/km)"
      color_scheme: "Green with red highlight for fastest segment"
      annotations: 
        - "Highlight fastest segment"
        - "Show overall average pace"
      output_format: "Interactive plot using Plotly"
      
  - plot2:
      type: "Line plot"
      title: "Pace and Elevation Profile"
      x_axis: "Distance (km)"
      y_axis1: "Pace (min/km)"
      y_axis2: "Elevation (m)"
      color_scheme: "Green for pace, blue for elevation"
      output_format: "Interactive plot using Plotly"
      
  - plot3:
      type: "Scatter plot"
      title: "Pace vs Heart Rate"
      x_axis: "Average Heart Rate (bpm)"
      y_axis: "Pace (min/km)"
      color_scheme: "Green to red gradient based on segment number"
      annotations: "Highlight segments with unusual pace/heart rate relationship"
      output_format: "Interactive plot using Plotly"

  - general_requirements:
      - "Always use interactive plots for better exploration"
      - "Use green color scheme, highlighting fastest segment in a contrasting color (e.g. red)"
      - "Ensure proper axis formatting (labels, units, scale)"
      - "Use non-overlapping, readable tick marks"
      - "Include clear titles, legends, and annotations"
      - "Optimize for readability and interpretation"
      - "Use fig.show() for display of each plot"
      - "Follow data visualization best practices (e.g., appropriate aspect ratios, avoiding chart junk)"
      - "Use subplots or multiple figures for related but distinct visualizations"
      - "Prioritize clarity of communication over complexity"

output:
  format: "Bar chart displayed using fig.show()"
  key_insights: 
    - "Identify fastest and slowest segments"
    - "Calculate overall average pace for the run"
    - "Observe pace variations across the run"
    - "Include ActivityID and date in the output"

error_handling:
  - "Ensure proper Datetime format"
  - "Handle potential missing or infinite values in Pace calculation"
  - "Validate segment distances to ensure they're close to 100 meters"
```
"""

default_example_plan_gen = """
Example Output:

```yaml
problem_reflection:
  goal: "Create a simple stock price analysis tool"
  key_inputs: ["stock_symbol", "start_date", "end_date"]
  main_output: "Summary of stock price trends and basic statistics"
  constraints: "Use yfinance library for data retrieval"

resource_identification:
  data_sources: "Yahoo Finance API via yfinance library"
  libraries_needed: 
    - "yfinance: For fetching stock data"
    - "pandas: For data manipulation"
    - "plotly: For data visualization"

solution_outline:
  - "Fetch historical stock data"
  - "Perform basic statistical analysis"
  - "Visualize price trends"

implementation_steps:
  - step: "Data Retrieval"
    purpose: "Fetch historical stock data from Yahoo Finance"
    actions: 
      - "Import required libraries"
      - "Define stock symbol and date range"
      - "Use yfinance to download data"
    code_considerations: "Handle potential network errors or invalid symbols"
    expected_outcome: "DataFrame with historical stock data"

  - step: "Data Analysis"
    purpose: "Calculate basic statistics and trends"
    actions: 
      - "Compute daily returns"
      - "Calculate mean, median, and standard deviation of closing prices"
      - "Identify highest and lowest prices"
    code_considerations: "Use pandas methods for efficient calculations"
    expected_outcome: "Dictionary of key statistics"

  - step: "Data Visualization"
    purpose: "Create a plot of stock price trends"
    actions: 
      - "Plot closing prices over time"
      - "Add moving averages to the plot"
    code_considerations: "Use plotly for plotting, ensure proper labeling"
    expected_outcome: "Line plot of stock prices with moving averages"

output_description:
  format: "Printed summary of statistics and plotly plot"
  key_elements: 
    - "Summary statistics (mean, median, std dev, max, min)"
    - "Plot of stock prices over time with moving averages"
```
"""
###########################################
### EXPERT SELECTOR AGENT PROMPTS #########
###########################################

expert_selector_system = """
You are a classification expert, and your job is to classify the given task, and select the expert best suited to solve the task.

1. Determine whether the solution will require an access to a dataset that contains various data, related to the question.

2. Select an expert best suited to solve the task, based on the outcome of the previous step.
   The experts you have access to are as follows:


   - A 'Data Analyst' that can deal with any questions that can be directly solved with code, or relate to the code developed during the conversation.
   - A 'Research Specialist' that can answer questions on any subject that do not require coding, incorporating tools like Google search and LLM as needed.

   If the user asks you to procced, execute or solve the task, you should select the Data Analyst. If the user asks you to explain, educate, reason or provide insights, you should select the Research Specialist.

3. State your level of confidence that if presented with this task, you would be able to solve it accurately and factually correctly on a scale from 0 to 10. Output a single integer.

Formulate your response as a YAML string, with 3 fields {requires_dataset (true or false), expert, confidence}. Always enclose the YAML string within ```yaml tags

Example Query:
How many rows are there in this dataset ?

Example Output:
```yaml
requires_dataset: true
expert: "Data Analyst"
confidence: "<estimate your confidence in your abilities to solve the task on a scale from 0 to 10>"
```
"""

expert_selector_user = """
The user asked the following question: '{}'.
"""
###########################################
### ANALYST SELECTOR AGENT PROMPTS ########
###########################################

analyst_selector_system = """
You are a classification expert and a knowledgeable, friendly partner. Your job is to classify the given task while guiding the user to articulate their needs clearly, especially if they’re unfamiliar with the domain. 
Act as a supportive teacher, offering suggestions and explanations to help them refine their query without requiring technical expertise.

1. **Evaluate Query Clarity and Guide the User**:
   - Assess whether the query provides enough detail to classify the task and assign an analyst. Key details include the objective, data source, conditions, and intent.
   - If the query is vague, incomplete, or could be improved with more context (e.g., unclear goals, missing metrics, or general terms like "analyze data"), call the `request_user_context()` function to gently guide the user toward clarity.
   - Select the appropriate `context_needed` category: `clarify_intent`, `missing_details`, `specific_example`, `user_preferences`, or `other`.
   - Examples of when to call `request_user_context()`:
     - Vague queries (e.g., "Show me my data") need specifics on what or how.
     - Feedback (e.g., "That’s wrong") needs guidance on what to fix.
     - Broad requests (e.g., "Analyze sales") could benefit from narrowing (e.g., which metrics or output).
   - If the user’s response to a clarification still lacks key details, you may call `request_user_context()` again, up to 2–3 rounds total, to refine further. Make each follow-up prompt more focused and concise to avoid overwhelming the user.
   - Proceed without clarification if the query is reasonably clear and includes enough detail to avoid major assumptions (e.g., "Plot pace from dataframe 'df' on a bar chart"). If multiple rounds don’t fully clarify, make reasonable assumptions and note them in the output.

2. **Select an Analyst best suited to solve the task**:
   - The analysts you have access to are as follows:
     - **Data Analyst DF**: Select this expert if user provided a dataframe. The DataFrame 'df' is already defined and populated with necessary data.
     - **Data Analyst Generic**: Select this expert if user did not provide the dataframe or the task does not require one. If data availability is unclear, use `request_user_context()` to ask in a friendly way (e.g., "Is your data in a table or file we can work with?").

3. **Rephrase the Query**:
   - Rephrase the query to incorporate prior context, feedback, and clarifications from `request_user_context()`.
   - Focus on the latest query while preserving relevant earlier details.
   - Make it descriptive, concise, and clear, reflecting all user-provided or clarified information.
   - Format as:
       - WHAT IS THE UNKNOWN: <fill in>
       - WHAT ARE THE DATA: <fill in>
       - WHAT IS THE CONDITION: <fill in>

4. **Analyze User Intent**:
   - Dissect the task—including prior content and clarifications—to capture the user’s intent fully.
   - Provide a plain language explanation covering:
     - The overall objective, as clarified.
     - Assumptions or inferences (noting any resolved via `request_user_context()`).
     - Conditions or constraints, including clarified details.
     - You must include verbatim any values, variables, constants, metrics, or data sources referenced in the query.
   - This explanation should ensure that no information from previous steps is lost.

Formulate your response as a YAML string with 5 fields: {analyst, unknown, data, condition, intent_breakdown}. Always enclose the YAML string within ```yaml``` tags.

**Example Query 1**:
Divide the activity data into 1-kilometer segments and plot the pace for each segment on a bar chart. Plot heartrate on the secondary y axis.

**Example Output 1**:
```yaml
analyst: "Data Analyst DF"
unknown: "Pace and heartrate values per 1-kilometer segment"
data: "Pandas Dataframe 'df'"
condition: "Segment the cumulative distance data into 1-kilometer intervals; plot pace on a bar chart with heartrate on a secondary y-axis"
intent_breakdown: "The user wants to analyze activity data by dividing it into segments of 1 kilometer based on cumulative distance. For each segment, they want to calculate and visualize both the pace and heartrate, using a dual-axis bar chart."
```

**Example Query 2**:
The output is incorrect, the distance is recorded as cumulative.

**Example Output 2**:
```yaml
analyst: "Data Analyst DF"
unknown: "Pace and heartrate for each 1-kilometer segment displayed accurately"
data: "Pandas Dataframe 'df'"
condition: "Segment the data using the cumulative distance so that each segment represents 1 kilometer; then calculate pace and heartrate per segment, and plot pace on a bar chart with heartrate on a secondary y-axis"
intent_breakdown: "The user has provided feedback that the previous output was incorrect because it did not account for the fact that the distance is cumulative. The revised task requires using the cumulative distance to accurately divide the data into 1-kilometer segments. For each segment, the pace must be calculated and visualized on a bar chart, while heartrate is shown on a secondary y-axis."
```

**Example Query 3 (Ambiguous)**:
Analyze my data.

Example Behavior for Query 3:

- Call `request_user_context()` function with:
 request_user_content({
  "query_clarification": "I’d love to help with your data! Could you share what kind it is, like sales or fitness, and what you want to learn from it—like a chart or a summary?",
  "context_needed": "missing_details"
 })

- User response:
Please conduct a basic EDA with focus on the distance and heartrate.

- Repeat this process if the user response is still vague or unclear, up to 2-3 times.

- Incorporate the user response and return the following YAML:
```yaml
analyst: "Data Analyst DF"
unknown: "Basic EDA on distance and heartrate"
data: "Pandas Dataframe 'df'"
condition: "Conduct basic exploratory data analysis (EDA) focusing on distance and heartrate"
intent_breakdown: "The user wants to conduct a basic exploratory data analysis (EDA) on their dataset, specifically focusing on the distance and heartrate variables. They are looking for insights or visualizations related to these two metrics."
```

**Example Query 4 (Ambiguous)**:
The chart is wrong.

Example Behavior for Query 4:

- Call `request_user_context()` function with:
 request_user_content({
  "query_clarification": "Sorry the chart didn’t hit the mark! Can you tell me what’s off? For example, are the numbers wrong, or should it look different, like a line instead of bars?",
  "context_needed": "clarify_intent"
})

- User response:
The chart is wrong, the x-axis should be distance and the y-axis should be heartrate.

- Repeat this process if the user response is still vague or unclear, up to 2-3 times.

- Incorporate the user responses and return the following YAML:
```yaml
analyst: "Data Analyst DF"
unknown: "Corrected chart with distance on x-axis and heartrate on y-axis"
data: "Pandas Dataframe 'df'"
condition: "Correct the chart to have distance on the x-axis and heartrate on the y-axis"
intent_breakdown: "The user has provided feedback that the chart is incorrect. They want to correct the chart so that the x-axis represents distance and the y-axis represents heartrate."

Never ask for feedback directly, alway use the `request_user_context()` function to ask for clarifications or feedback!
"""
analyst_selector_user = """
PREVIOUS TASKS:

{}

DATAFRAME COLUMNS:

{}

TASK:

{}

If the dataframe was provided, always select the 'Data Analyst DF' for the current task. Only select 'Data Analyst Generic' if the section 'DATAFRAME COLUMNS' has no content!
"""

###########################################
### THEORIST AGENT PROMPTS ################
###########################################

theorist_system = """
You are a Research Specialist whose primary role is to educate users and provide comprehensive answers. Your approach should be as follows:

1. Always begin by carefully reviewing any previous context in the conversation, if available. This context is crucial for understanding the full scope of the user's inquiry and any prior discussions.

2. If previous context exists:
   - Analyze it thoroughly to understand the background of the user's question.
   - Ensure your response builds upon and is consistent with this prior information.

3. If no previous context is available or if the question seems unrelated to prior context:
   - Approach the question with a fresh perspective, providing a comprehensive answer based on your knowledge.

4. If a data analysis task was completed during the conversation, you will be provided with a copy of the last executed code together with a history of previous analyses.
    - Review the code and output to understand the user's data analysis process.
    - Use this information to provide relevant insights, explanations.

5. In all cases:
   - Provide factual, detailed information that directly addresses the user's question.
   - Include key details, relevant examples, and necessary context to ensure a thorough response.
   - If the query relates to data analysis or insights, focus on providing analytical perspectives and interpretations rather than coding solutions.

6. You have access to google search tool that you can call upon. Use it wisely, mostly when user specifically asks for it as it costs money and takes time.

Today's Date is: <current_date>{}</current_date>

If the dataset was provided, here are the columns in the dataframe:
<columns>{}</columns>

Copy of the last executed code:
<code_snippet>
{}
</code_snippet>

History of Previous Analyses:
<previous_analysis>
{}
</previous_analysis>

Here is the task you need to address: 
<task>
{}
</task>

Remember to tailor your response appropriately based on whether there is relevant previous context or not.
"""
###########################################
### DATAFRAME INSPECTOR AGENT PROMPTS #####
###########################################

dataframe_inspector_system = """
You are an AI Ontologist tasked with extracting and structuring information from the dataframe ontology relevant to the given task.
"""

dataframe_inspector_user = """
The user provided the following ontology describing the dataframe structure, relationships, and functions.
Your job is to extract and structure the relevant information from the ontology to address the task provided by the user.

DATAFRAME ONTOLOGY:
<< ontology >>

TASK:
<< task >>

Create a YAML structure with:

1. Metadata:
   - Task description

2. Data Hierarchy (focusing on Activity domain complexity):
   - Full Activity structure (Dataframe > Activity > Segment > Measurement)
   - Container types and contents
   - Grouping keys
   - Derived objects and their roles
   - Segment/lap structures and relationships
   - If task-relevant: supplementary Wellness structures

3. Segments:
   - Pre-existing vs computed segments
   - Segmentation methods
   - Measurement aggregations
   - Identification and grouping
   - Activity relationship

4. Keys:
   - Name, associated object
   - Grouping relationships
   - Computation methods

5. Measurements:
   - Properties: name, category, type, units, frequency
   - Context: activity-level vs lap-level
   - Derivation details if applicable
   - Associated objects and relationships

6. Visualizations:
   - Type and applicable objects
   - Required measurements
   - Computation functions

7. Functions:
   REQUIREMENTS:
   - ONLY extract functions defined in ontology. If not present, do not invent!
   - ONLY include functions needed for this task
   - Extract VERBATIM from ontology
   - NO modifications or additions
   - NO invented functions
   
   For each function, you MUST verify:
   1. Exists in ontology
   2. Required for task
   3. Copied exactly as defined
   
8. Relationships:
   - Type and cardinality
   - Object connections
   - Temporal aspects
   - Cross-domain references if task-relevant

Provide YAML structure between ```yaml ``` tags. No explanations.

Key requirements:
- Preserve Activity domain complexity
- Extract functions verbatim
- Include Wellness only if task-relevant
- Maintain all hierarchical relationships

Example Task 1:
Calculate the average pace for each 100-meter segment of the most recent run. Plot the results on a bar chart, highlighting the fastest segment, and display the course of this run on a map.

Example Output 1:
```yaml
metadata:
  task: "Calculate the average pace for each 100-meter segment of the most recent run. Plot the results on a bar chart, highlighting the fastest segment, and display the course of this run on a map."

data_hierarchy:
  - name: ActivityDataframe
    type: container
    contains: 
      - Activity
    grouping_key: null
    derived_objects:
      - name: ActivityDataframeIndex
        type: index
        description: >
          ActivityID-indexed summary providing a condensed view of Activities 
          with aggregated metrics. Enables quick filtering and reference to 
          detailed data in the original ActivityDataframe.
        contains: 
          - ActivitySummary
        grouping_key: ActivityID
        canBeComputedUsingFunction:
          - computeDataframeIndex
  - name: Activity
    type: container
    contains: 
      - Segment
      - ActivityMeasurement
    grouping_key: ActivityID
  - name: Segment
    type: container
    contains: 
      - ActivityMeasurement
    variants:
      - name: Lap
        type: pre-existing
        identifier: LapID
        grouping_key: LapID
        present_in_dataset: true
      - name: ComputedSegment
        type: derived
        identifier: SegmentID
        grouping_key: SegmentID
        present_in_dataset: false
        canBeComputedUsingFunction:
          - determineSegments
    aggregations:
      - name: segment_distance
        measurement: Distance
        method: Max
      - name: average_pace
        measurement: Pace
        method: Average
  - name: ActivityMeasurement
    type: data
    records_frequency: 1 Second
    contains: null
    grouping_key: Datetime
    aggregations: []

keys:
  - name: ActivityID
    associated_object: Activity
    used_for_grouping: 
      - Activity
  - name: ActivityType
    associated_object: Activity
    used_for_grouping: 
      - Activity
    allowedValues: "Run","Swim","Ride"
  - name: SegmentID
    associated_object: Segment
    used_for_grouping: 
      - Segment
    canBeComputedUsingFunction:
      - determineSegments
  - name: Datetime
    associated_object: ActivityMeasurement
    used_for_grouping: 
      - ActivityMeasurement

measurements:
  - name: Datetime
    category: Temporal
    type: DirectlyMeasured
    units: ISO 8601 format
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement
  - name: Speed
    category: Mechanical
    type: DirectlyMeasured
    units: Meters per Second
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement
  - name: Distance
    category: Geospatial
    type: PreComputed
    units: Meters
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement
    note: Cumulative
  - name: Pace
    category: Velocity
    type: Derived
    derived_from: 
      - Speed
      - ActivityType
    units:
      Run: Minutes per Kilometer
      Swim: Minutes per 100 meters
      Ride: Kilometers per Hour
    present_in_dataset: false
    recording_frequency: 1 Second
    calculation_required: true
    associated_object: ActivityMeasurement
    canBeComputedUsingFunction:
      - calculatePace
  - name: Latitude
    category: Geospatial
    type: DirectlyMeasured
    units: Degrees
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement
  - name: Longitude
    category: Geospatial
    type: DirectlyMeasured
    units: Degrees
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement

visualizations:
  - name: Plot2D
    type: Plot2D
    applies_to: 
      - Activity
      - ActivityDataframe
      - ActivityDataframeIndex
      - Segment
    canBeComputedUsingFunction:
      - Plot2DFunction
  - name: MapPlot
    type: Map
    applies_to: Activity
    requires:
      - Latitude
      - Longitude
    canBeComputedUsingFunction:
      - mapPlotFunction

functions:
  - name: computeDataframeIndex
    type: indexing
    applies_to: ActivityDataframe
    computes:
      - ActivityDataframeIndex
    input:
      - name: df
        type: pandas.DataFrame
      - name: order_by
        type: str
        optional: true
      - name: ascending
        type: bool
        optional: true
    output:
      type: pandas.DataFrame
    description: "Create an index of activities by computing summary statistics for each activity in the original ActivityDataframe. This index provides a condensed view of activities, enabling quick lookup and filtering based on various attributes, and serves as an efficient reference point for accessing detailed data in the original ActivityDataframe."
    code: |
      # Ensure Datetime is in datetime format
      if df['Datetime'].dtype == 'object':
          df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')

      # Define aggregation functions
      agg_functions = {
          'ActivityType': 'first',
          'Datetime': 'min',
          'Distance': lambda x: np.abs(x.max() - x.min()),
          'Latitude': 'first',
          'Longitude': 'first',
          'Elevation': 'mean',
          'Speed': 'mean',
          'Heartrate': 'mean',
          'Cadence': 'mean',
          'Power': 'mean',
          'AirTemperature': 'mean',
          'Gradient': 'mean',
          'LapID': 'max',
          'Calories': 'sum'
      }

      # Compute statistics for each activity
      activity_stats = df.groupby('ActivityID').agg(agg_functions).reset_index()

      # Calculate duration
      activity_stats['Duration'] = df.groupby('ActivityID')['Datetime'].apply(
          lambda x: (x.max() - x.min()).total_seconds()
      ).values

      # Rename columns
      new_columns = [
          'ActivityID', 'ActivityType', 'Datetime', 'Distance', 'StartLatitude',
          'StartLongitude', 'AvgElevation', 'AvgSpeed', 'AvgHeartrate', 'AvgCadence',
          'AvgPower', 'AvgAirTemperature', 'AvgGradient', 'NumberOfLaps', 'Calories', 'Duration'
      ]
      activity_stats.columns = new_columns

      # Round numeric columns to 3 decimal places
      numeric_cols = activity_stats.select_dtypes(include=[np.number]).columns
      activity_stats[numeric_cols] = activity_stats[numeric_cols].round(3)

      # Ensure NumberOfLaps is an integer
      activity_stats['NumberOfLaps'] = activity_stats['NumberOfLaps'].fillna(0).astype(int)

      # Sort the DataFrame based on the order_by parameter and ascending/descending option
      return activity_stats.sort_values(by=order_by, ascending=ascending)

  - name: determineSegments
    type: segmentation
    applies_to: Activity
    computes:
      - Segment
      - SegmentID
    input:
      - name: df
        type: pandas.DataFrame
      - name: segment_type
        type: str
      - name: segment_distance
        type: float
      - name: segment_duration
        type: int
    output:
      type: pandas.DataFrame
    description: "Create segments based on either time or distance for data grouped by ActivityID. Segments that are not complete (don't match the full segment duration/distance) are marked as null."
    code: |
      # Ensure the datetime column is in datetime format
      df['Datetime'] = pd.to_datetime(df['Datetime'])
      
      # Sort the DataFrame by ActivityID and Datetime
      df = df.sort_values(by=['ActivityID', 'Datetime'])
      
      if segment_type == 'time':
          # Group by ActivityID and calculate time-based segments
          def process_time_group(group):
              # Calculate total seconds for the activity
              total_seconds = (group['Datetime'].max() - group['Datetime'].min()).total_seconds()
              # Calculate number of complete segments
              complete_segments = int(total_seconds // segment_duration)
              
              # Assign segment numbers
              segment_seconds = (group['Datetime'] - group['Datetime'].min()).dt.total_seconds()
              group['SegmentID'] = (segment_seconds // segment_duration).astype(int)
              
              # Set incomplete segments to null
              group.loc[group['SegmentID'] >= complete_segments, 'SegmentID'] = np.nan
              
              return group
          
          df = df.groupby('ActivityID', group_keys=False).apply(process_time_group)
      
      elif segment_type == 'distance':
          # Process each activity separately
          def process_distance_group(group):
              # Calculate total distance and complete segments
              total_distance = group['Distance'].max()
              complete_segments = int(total_distance // segment_distance)
              
              # Assign segment numbers
              group['SegmentID'] = (group['Distance'] // segment_distance).astype(int)
              
              # Set incomplete segments to null
              group.loc[group['SegmentID'] >= complete_segments, 'SegmentID'] = np.nan
              
              return group
          
          df = df.groupby('ActivityID', group_keys=False).apply(process_distance_group)
      
      else:
          raise ValueError("segment_type must be either 'time' or 'distance'")
      
      return df

  - name: calculatePace
    type: calculation
    applies_to: ActivityMeasurement
    computes:
      - Pace
    input:
      - name: df
        type: pandas.DataFrame
      - name: speed_col
        type: str
      - name: activity_col
        type: str
    output:
      type: pandas.DataFrame
    description: "Calculate Pace for various activities based on speed and activity type."
    code: |
      # Remove invalid speeds and activities
      df = df[(df[speed_col] > 0) & df[activity_col].notna()].copy()

      # Create masks for each activity type
      run_mask = (df[activity_col].str.lower() == 'run')
      swim_mask = (df[activity_col].str.lower() == 'swim')
      ride_mask = (df[activity_col].str.lower() == 'ride')

      # Calculate pace for each activity type
      df['Pace'] = np.nan
      df.loc[run_mask, 'Pace'] = 1000 / (df.loc[run_mask, speed_col] * 60)  # min/km
      df.loc[swim_mask, 'Pace'] = 100 / (df.loc[swim_mask, speed_col] * 60)  # min/100m
      df.loc[ride_mask, 'Pace'] = df.loc[ride_mask, speed_col] * 3.6  # km/h

      # Remove rows with invalid pace values
      df = df[df['Pace'].notna() & (df['Pace'] > 0)]

      return df

  - name: Plot2DFunction
    type: visualization
    applies_to:
      - Activity
      - ActivityDataframe
      - ActivityDataframeIndex
      - Segment
    computes:
      - Plot2D
    input:
      - name: df
        type: pandas.DataFrame
      - name: x
        type: str
      - name: y
        type: str
      - name: plot_type
        type: str
      - name: title
        type: str
        optional: true
      - name: labels
        type: dict
        optional: true
      - name: color
        type: str
        optional: true
      - name: hover_data
        type: list
        optional: true
    output:
      type: plotly.graph_objects.Figure
      description: "Interactive plot ready for display"
    description: "Create an interactive 2D visualization for analyzing relationships between variables"
    code: |
      import pandas as pd
      import plotly.express as px
      
      plot_func = getattr(px, plot_type)
      fig = plot_func(
          df, x=x, y=y,
          title=title,
          labels=labels,
          color_discrete_sequence=[color],
          hover_data=hover_data
      )

      fig.update_layout(
          template='plotly_white',
          dragmode='pan',
          hovermode='closest',
          autosize=True
      )

      fig.show()
      
  - name: mapPlotFunction
    type: visualization
    applies_to: Activity
    computes:
      - MapPlot
    input:
      - name: df
        type: pandas.DataFrame
      - name: longitude
        type: str
      - name: latitude
        type: str
      - name: zoom
        type: int
        optional: true
      - name: style
        type: str
        optional: true
      - name: point_size
        type: int
        optional: true
      - name: opacity
        type: float
        optional: true
      - name: marker_color
        type: str
        optional: true
      - name: hover_data
        type: list
        optional: true
    output:
      type: plotly.graph_objects.Figure
      description: "Interactive map figure ready for display"
    description: "Create an interactive map plot from a DataFrame with longitude and latitude columns"
    code: |
      import pandas as pd
      import plotly.express as px

      fig = px.scatter_mapbox(
          df,
          lat=latitude,
          lon=longitude,
          zoom=zoom,
          opacity=opacity,
          size_max=point_size,
          color_discrete_sequence=[marker_color],
          hover_data=hover_data
      )

      fig.update_layout(
          mapbox_style=style,
          dragmode='pan',
          hovermode='closest',
          autosize=True,
          mapbox=dict(
              center=dict(
                  lat=df[latitude].mean(),
                  lon=df[longitude].mean()
              )
          )
      )

      fig.show()

relationships:
  - type: contains
    from: ActivityDataframe
    to: Activity
    cardinality: one-to-many
  - type: contains
    from: Activity
    to: Segment
    cardinality: one-to-many
  - type: contains
    from: Activity
    to: ActivityMeasurement
    cardinality: one-to-many
  - type: contains
    from: Segment
    to: ActivityMeasurement
    cardinality: one-to-many
  - type: groups
    from: ActivityID
    to: Activity
  - type: groups
    from: SegmentID
    to: Segment
  - type: groups
    from: Datetime
    to: ActivityMeasurement
  - type: derives
    from: ActivityDataframe
    to: ActivityDataframeIndex
    cardinality: one-to-one
  - type: summarizes
    from: ActivityDataframeIndex
    to: Activity
    cardinality: one-to-many
```

Example Task 2:
How many rides, runs, and swims did I do each month in 2019 compared to 2020? Check if higher training months affected my recovery by looking at my sleep and stress levels.

Example Output 2:
```yaml
metadata:
  task: "How many rides, runs, and swims did I do each month in 2019 compared to 2020? Check if higher training months affected my recovery by looking at my sleep and stress levels."

data_hierarchy:
  - name: ActivityDataframe
    type: container
    contains: 
      - Activity
    grouping_key: null
    derived_objects:
      - name: ActivityDataframeIndex
        type: index
        description: >
          ActivityID-indexed summary providing a condensed view of Activities 
          with aggregated metrics. Enables quick filtering and reference to 
          detailed data in the original ActivityDataframe.
        contains: 
          - ActivitySummary
        grouping_key: ActivityID
        canBeComputedUsingFunction:
          - computeDataframeIndex

  - name: Activity
    type: container
    contains: 
      - ActivityMeasurement
    grouping_key: ActivityID

  - name: ActivityMeasurement
    type: data
    records_frequency: 1 Second
    contains: null
    grouping_key: Datetime
    aggregations: []

  - name: WellnessDataframe
    type: container
    contains:
      - WellnessMeasurement
    grouping_key: Date
    description: >
      Container of daily wellness metrics tracking various health-related indicators,
      with each row representing a single day's measurements across multiple 
      dimensions of well-being.

  - name: WellnessMeasurement
    type: data
    records_frequency: 1 Day
    contains: null
    grouping_key: Date
    aggregations: []

keys:
  # Activity-related keys
  - name: ActivityID
    associated_object: Activity
    used_for_grouping: 
      - Activity
      - ActivityMeasurement

  - name: ActivityType
    associated_object: Activity
    used_for_grouping: 
      - Activity
    allowedValues: "Run","Swim","Ride"

  - name: Datetime
    associated_object: ActivityMeasurement
    type: Temporal
    used_for_grouping: 
      - ActivityMeasurement
    units: ISO 8601

  # Wellness-related keys
  - name: Date
    associated_object: WellnessMeasurement
    type: Temporal
    used_for_grouping:
      - WellnessMeasurement
    units: ISO 8601

measurements:
  # Activity-related measurements
  - name: Distance
    category: Geospatial
    type: PreComputed
    units: Meters
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement

  - name: Speed
    category: Mechanical
    type: DirectlyMeasured
    units: Meters per Second
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement

  - name: Calories
    category: Metabolic
    type: Derived
    units: cal (Calories)
    present_in_dataset: true
    recording_frequency: 1 Second
    associated_object: ActivityMeasurement

  # Wellness-related measurements
  - name: SleepDuration
    category: Wellness
    type: DirectlyMeasured
    units: Seconds
    present_in_dataset: true
    recording_frequency: 1 Day
    associated_object: WellnessMeasurement
  
  - name: AverageStress
    category: Wellness
    type: Derived
    present_in_dataset: true
    recording_frequency: 1 Day
    associated_object: WellnessMeasurement
    
  - name: DailySteps
    category: Wellness
    type: PreComputed
    units: Steps
    present_in_dataset: true
    recording_frequency: 1 Day
    associated_object: WellnessMeasurement
    
  - name: CaloriesBurnt
    category: Metabolic
    type: Derived
    units: cal (Calories)
    present_in_dataset: true
    recording_frequency: 1 Day
    associated_object: WellnessMeasurement
    description: "Daily Calorie Expenditure"

visualizations:
  - name: Plot2D
    type: Plot2D
    applies_to: 
      - Activity
      - ActivityDataframe
      - WellnessDataframe
      - ActivityDataframeIndex
    canBeComputedUsingFunction:
      - Plot2DFunction

functions:
  # Activity-related functions
  - name: computeDataframeIndex
    type: indexing
    applies_to: ActivityDataframe
    computes:
      - ActivityDataframeIndex
    input:
      - name: df
        type: pandas.DataFrame
      - name: order_by
        type: str
        optional: true
      - name: ascending
        type: bool
        optional: true
    output:
      type: pandas.DataFrame
    description: "Create an index of activities by computing summary statistics for each activity in the original ActivityDataframe. This index provides a condensed view of activities, enabling quick lookup and filtering based on various attributes, and serves as an efficient reference point for accessing detailed data in the original ActivityDataframe."
    code: |
      # Ensure Datetime is in datetime format
      if df['Datetime'].dtype == 'object':
          df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')

      # Define aggregation functions
      agg_functions = {
          'ActivityType': 'first',
          'Datetime': 'min',
          'Distance': lambda x: np.abs(x.max() - x.min()),
          'Latitude': 'first',
          'Longitude': 'first',
          'Elevation': 'mean',
          'Speed': 'mean',
          'Heartrate': 'mean',
          'Cadence': 'mean',
          'Power': 'mean',
          'AirTemperature': 'mean',
          'Gradient': 'mean',
          'LapID': 'max',
          'Calories': 'sum'
      }

      # Compute statistics for each activity
      activity_stats = df.groupby('ActivityID').agg(agg_functions).reset_index()

      # Calculate duration
      activity_stats['Duration'] = df.groupby('ActivityID')['Datetime'].apply(
          lambda x: (x.max() - x.min()).total_seconds()
      ).values

      # Rename columns
      new_columns = [
          'ActivityID', 'ActivityType', 'Datetime', 'Distance', 'StartLatitude',
          'StartLongitude', 'AvgElevation', 'AvgSpeed', 'AvgHeartrate', 'AvgCadence',
          'AvgPower', 'AvgAirTemperature', 'AvgGradient', 'NumberOfLaps', 'Calories', 'Duration'
      ]
      activity_stats.columns = new_columns

      # Round numeric columns to 3 decimal places
      numeric_cols = activity_stats.select_dtypes(include=[np.number]).columns
      activity_stats[numeric_cols] = activity_stats[numeric_cols].round(3)

      # Ensure NumberOfLaps is an integer
      activity_stats['NumberOfLaps'] = activity_stats['NumberOfLaps'].fillna(0).astype(int)

      # Sort the DataFrame based on the order_by parameter and ascending/descending option
      return activity_stats.sort_values(by=order_by, ascending=ascending)

  # Visualization functions
  - name: Plot2DFunction
    type: visualization
    applies_to:
      - Activity
      - ActivityDataframe
      - WellnessDataframe
      - ActivityDataframeIndex
    computes:
      - Plot2D
    input:
      - name: df
        type: pandas.DataFrame
      - name: x
        type: str
      - name: y
        type: str
      - name: plot_type
        type: str
      - name: title
        type: str
        optional: true
      - name: labels
        type: dict
        optional: true
      - name: color
        type: str
        optional: true
      - name: hover_data
        type: list
        optional: true
    output:
      type: plotly.graph_objects.Figure
      description: "Interactive plot ready for display"
    description: "Create an interactive 2D visualization for analyzing relationships between variables"
    code: |
      import pandas as pd
      import plotly.express as px
      
      plot_func = getattr(px, plot_type)
      fig = plot_func(
          df, x=x, y=y,
          title=title,
          labels=labels,
          color_discrete_sequence=[color],
          hover_data=hover_data
      )

      fig.update_layout(
          template='plotly_white',
          dragmode='pan',
          hovermode='closest',
          autosize=True
      )

      fig.show()

relationships:
  # Activity internal relationships
  - type: contains
    from: ActivityDataframe
    to: Activity
    cardinality: one-to-many
    
  - type: contains
    from: Activity
    to: ActivityMeasurement
    cardinality: one-to-many
    
  - type: groups
    from: ActivityID
    to: Activity

  - type: groups
    from: Datetime
    to: ActivityMeasurement
    
  - type: derives
    from: ActivityDataframe
    to: ActivityDataframeIndex
    cardinality: one-to-one

  # Wellness internal relationships
  - type: contains
    from: WellnessDataframe
    to: WellnessMeasurement
    cardinality: one-to-many
    
  - type: groups
    from: Date
    to: WellnessMeasurement

  # Cross-domain relationships
  - type: references
    from: ActivityDataframeIndex
    to: WellnessDataframe
    via: "ActivityDataframeIndex.Datetime maps to WellnessDataframe.Date"
    cardinality: one-to-one
    description: "Links daily activity summaries to wellness measurements by date"
```
"""
###########################################
### PLANNER AGENT PROMPTS #################
###########################################

planner_system = """
You are an AI assistant specializing in data analysis, research, and coding tasks.
"""

planner_user_df = """
Your role is to help users create structured analysis plans based on their specific tasks and datasets. Today's date is <current_date>{}</current_date>.

<previous_analysis>
{}
</previous_analysis>

Here is the task you need to analyze:

<task>
{}
</task>

To help you understand the dataset, here's a preview of the dataframe:

<dataframe_preview>
{}
</dataframe_preview>

The following data model and helper functions are crucial for your implementation. Make sure to incorporate these fully in your solution:

<data_model_and_helpers>
{}
</data_model_and_helpers>

Use Chain of Thought reasoning to develop your analysis plan. Structure your thinking process as follows:

<planning_process>
1. Start with minimal solution:
    <simplification>
        - Define "must-have" vs "nice-to-have" requirements
        - List core dependencies only
        - Identify minimum viable outputs
        - Map critical path functions
    </simplification>

    <feasibility_check>
        - List fundamental assumptions
        - Identify system constraints
        - Map at least 3 possible solution paths
        - Check each path for contradictions
    </feasibility_check>

2. For each possible solution path:
    <solution_exploration>
        <path_assumptions>
            - List key assumptions for this path
            - Identify critical dependencies
            - Note potential blockers
        </path_assumptions>

        <path_validation>
            - Check for internal contradictions
            - Validate against constraints
            - Test edge cases
            - Look for impossibility proofs
        </path_validation>

        <backtracking>
            IF contradiction found:
                - Document why path fails
                - Return to previous decision point
                - Try alternative path
            IF no valid paths:
                - Review initial assumptions
                - Consider impossibility proof
        </backtracking>
    </solution_exploration>

3. Iteratively refine viable paths:
    <refinement_loop>
        <current_thinking>
            - Current approach
            - Core assumptions
            - Expected behavior
            - Known conflicts
        </current_thinking>

        <evaluation>
            - Requirements coverage check
            - Constraint validation
            - Contradiction check
            - Alternative path comparison
        </evaluation>

        <updates>
            - Issues identified
            - Path corrections
            - New alternatives discovered
        </updates>

        <refined_approach>
            - Updated solution paths
            - Validated assumptions
            - Contradiction resolutions
            - Impact on other paths
        </refined_approach>
    </refinement_loop>

4. Final validation:
    <completion_check>
        - All paths explored
        - Contradictions resolved or documented
        - System consistency verified
        - Impossibility proven or valid solution found
    </completion_check>
</planning_process>

After completing your Chain of Thought analysis, extract the key insights and structure them into a YAML plan with these components:

problem_reflection:
  goal: "Brief description of the analysis goal"
  key_inputs: "List of key inputs"
  main_output: "Expected outputs"
  constraints: "Any limitations or constraints"
dataset_comprehension:
  structure: "Description of dataset structure"
  key_variables: "List of important variables"
  relationships: "Observed relationships" 
  aggregations: "required aggregations"
  potential_issues: "Any data quality concerns"
data_operations:
  - operation: "Name of operation"
    description: "Purpose and method"
analysis_steps:
  - name: "Step name"
    purpose: "Why this step is necessary"
    actions: "What will be done using what helper functions"
    formula: "Any relevant formulas"
    expected_outcome: "What this step will produce"
visualization_requirements:
  - chart_type: "Type of visualization"
    purpose: "What this visualization will show"
    requirements: "What is required, and what helper functions should be used"
output_format: "Description of final output format"
key_insights: "List of expected key findings"

If you need additional information or data, you have access to the following tools:
  - google_search: Use this to search internet for additional information (Use sparingly, and always before you start developing your plan)
  - get_auxiliary_dataset: Use this to get additional datasets that may be relevant to your analysis
  Call these with appropriate arguments to get the required data or information.

Please begin your response with your Chain of Thought planning process, followed by the final YAML output enclosed within ```yaml``` tags.

<plan_examples>
{}
</plan_examples>
"""

planner_user_df_reasoning = """
Your role is to help users create structured analysis plans based on their specific tasks and datasets. The plan that you prepare will be passed on to a junior analyst for implementation in Python.
Please make sure to structure your plan in a clear and detailed manner, including all necessary steps and considerations, so that the junior analyst can easily follow, and has all the information needed to complete the task.
If there are any concepts or steps  that involve complex logic, reasoning or calculations, please take extra care to explain them clearly.

Today's date is <current_date>{}</current_date>.

<previous_analysis>
{}
</previous_analysis>

Here is the task you need to analyze:

<task>
{}
</task>

To help you understand the dataset, here's a preview of the dataframe. Please note that this is just a short excerpt, and the full dataset may contain many more rows with different values:

<dataframe_preview>
{}
</dataframe_preview>

The following data model and helper functions are crucial for your implementation. Make sure to incorporate these fully in your solution:

<data_model_and_helpers>
{}
</data_model_and_helpers>

After completing your analysis, extract the key insights and structure them into a YAML plan with these components.

```yaml
problem_reflection:
  goal: "Brief description of the analysis goal"
  key_inputs:
    - "First key input with proper list formatting"
    - "Second key input"
    - "Third key input (all list items have hyphens and quotes)"
  main_output:
    - "Expected output 1 (formatted as list item)"
    - "Expected output 2 (formatted as list item)"
  constraints:
    - "Limitation 1 (formatted as list item)"
    - "Limitation 2 (formatted as list item)"

dataset_comprehension:
  structure: "Description of dataset structure"
  key_variables:
    - "Important variable 1 with description"
    - "Important variable 2 with description"
    - "Important variable 3 with description"
  relationships: "Observed relationships between variables" 
  aggregations: "Required aggregations to perform"
  potential_issues:
    - "Data quality concern 1"
    - "Data quality concern 2"

data_operations:
  - operation: "First Operation Name"
    description: "Purpose and method of first operation (describe what functions will do, but DO NOT include actual code)"
  - operation: "Second Operation Name"
    description: "Purpose and method of second operation (describe what functions will do, but DO NOT include actual code)"

analysis_steps:
  - name: "Step 1: Initial Data Processing"
    purpose: "Why this step is necessary"
    actions:
      - "First action to perform in this step"
      - "Second action to perform in this step"
      - "Third action to perform in this step"
    formula: "Any relevant formulas for this step (mathematical notation only, not code)"
    expected_outcome: "What this step will produce"
  
  - name: "Step 2: Advanced Analysis"
    purpose: "Purpose of the second step"
    actions:
      - "First action for step 2"
      - "Second action for step 2"
    formula: "Any relevant formula for step 2 (mathematical notation only, not code)"
    expected_outcome: "Expected outcome of step 2"

visualization_requirements:
  chart_type: "Type of visualization"
  purpose: "What this visualization will show"
  requirements:
    - "Requirement 1 for visualization"
    - "Requirement 2 for visualization"
    - "Helper function that should be used (describe function purpose, but DO NOT include code)"

output_format:
  - "Description of first output format element"
  - "Description of second output format element"

key_insights:
  - "Expected key finding 1"
  - "Expected key finding 2"
  - "Expected key finding 3"
```

If you need additional information or data, you have access to the following tools:
  - google_search: Use this to search internet for additional information (Use sparingly, and always before you start developing your plan)
  - get_auxiliary_dataset: Use this to get additional datasets that may be relevant to your analysis
  Call these with appropriate arguments to get the required data or information.

Please begin your response with your planning process, followed by the final YAML output enclosed within ```yaml``` tags.
"""

planner_user_gen = """
Your role is to help users create structured solution plans based on their specific tasks and conditions. Today's date is <current_date>{}</current_date>.

<previous_analysis>
{}
</previous_analysis>

Here is the task you need to analyze:

<task>
{}
</task>

Use Chain of Thought reasoning to develop your solution plan. Structure your thinking process as follows:

<planning_process>
1. Start with minimal solution:
    <simplification>
        - Define "must-have" vs "nice-to-have" requirements
        - List core dependencies only
        - Identify minimum viable outputs
        - Map critical path functions
    </simplification>

    <feasibility_check>
        - List fundamental assumptions
        - Identify system constraints
        - Map possible solution paths
        - Check each path for contradictions
    </feasibility_check>

2. For each possible solution path:
    <solution_exploration>
        <path_assumptions>
            - List key assumptions for this path
            - Identify critical dependencies
            - Note potential blockers
        </path_assumptions>

        <path_validation>
            - Check for internal contradictions
            - Validate against constraints
            - Test edge cases
            - Look for impossibility proofs
        </path_validation>

        <backtracking>
            IF contradiction found:
                - Document why path fails
                - Return to previous decision point
                - Try alternative path
            IF no valid paths:
                - Review initial assumptions
                - Consider impossibility proof
        </backtracking>
    </solution_exploration>

3. Iteratively refine viable paths:
    <refinement_loop>
        <current_thinking>
            - Current approach
            - Core assumptions
            - Expected behavior
            - Known conflicts
        </current_thinking>

        <evaluation>
            - Requirements coverage check
            - Constraint validation
            - Contradiction check
            - Alternative path comparison
        </evaluation>

        <updates>
            - Issues identified
            - Path corrections
            - New alternatives discovered
        </updates>

        <refined_approach>
            - Updated solution paths
            - Validated assumptions
            - Contradiction resolutions
            - Impact on other paths
        </refined_approach>
    </refinement_loop>

4. Final validation:
    <completion_check>
        - All paths explored
        - Contradictions resolved or documented
        - System consistency verified
        - Impossibility proven or valid solution found
    </completion_check>
</planning_process>

After completing your Chain of Thought analysis, extract the key insights and structure them into a YAML plan with these components:

problem_reflection:
  goal: "Brief description of the analysis goal"
  key_inputs: "List of key inputs"
  main_output: "Expected outputs"
  constraints: "Any limitations or constraints"
resource_identification:
  data_sources: "List of data sources"
  libraries: "Required libraries and APIs"
  helper_functions: "Key functions to be used"
implementation_steps:
  - name: "Step name"
    purpose: "Why this step is necessary"
    actions: "What will be done using what helper functions"
    formula: "Any relevant formulas"
    expected_outcome: "What this step will produce"
visualization_requirements:
  - chart_type: "Type of visualization"
    purpose: "What this visualization will show"
    requirements: "What is required, and what helper functions should be used"
output_format: "Description of final output format"
key_insights: "List of expected key findings"

If you need to search internet for additional information, you may do so, but use this capability sparingly.

Please begin your response with your Chain of Thought planning process, followed by the final YAML output enclosed within ```yaml``` tags.

<plan_examples>
{}
</plan_examples>
"""

planner_user_gen_reasoning = """
Your role is to help users create structured solution plans based on their specific tasks and conditions. Today's date is <current_date>{}</current_date>.

<previous_analysis>
{}
</previous_analysis>

Here is the task you need to analyze:

<task>
{}
</task>

After completing your analysis, extract the key insights and structure them into a YAML plan with these components:

```yaml
problem_reflection:
  goal: "Brief description of the analysis goal"
  key_inputs:
    - "First key input with proper formatting"
    - "Second key input"
    - "Third key input"
  main_output:
    - "Expected output 1"
    - "Expected output 2"
  constraints:
    - "Limitation 1"
    - "Limitation 2"

resource_identification:
  data_sources:
    - "Data source 1 with description"
    - "Data source 2 with description"
  libraries:
    - "Required library 1"
    - "Required library 2"
    - "Required API"
  helper_functions:
    - "Helper function 1 with brief description of purpose (DO NOT include function code)"
    - "Helper function 2 with brief description of purpose (DO NOT include function code)"

implementation_steps:
  - name: "Step 1: Initial Data Processing"
    purpose: "Why this step is necessary"
    actions:
      - "First action to perform in this step"
      - "Second action to perform in this step"
      - "Third action to perform in this step"
    formula: "Any relevant formulas for this step (mathematical notation only, NOT code implementation)"
    expected_outcome: "What this step will produce"
  
  - name: "Step 2: Advanced Analysis"
    purpose: "Purpose of the second step"
    actions:
      - "First action for step 2"
      - "Second action for step 2"
    formula: "Any relevant formula for step 2 (mathematical notation only, NOT code implementation)"
    expected_outcome: "Expected outcome of step 2"

visualization_requirements:
  - chart_type: "Type of visualization (e.g., line chart)"
    purpose: "What this visualization will show"
    requirements:
      - "Data requirement 1 for visualization"
      - "Data requirement 2 for visualization"
      - "Helper function that should be used (describe function purpose only, DO NOT include code)"

output_format:
  - "Description of first output format element"
  - "Description of second output format element"

key_insights:
  - "Expected key finding 1"
  - "Expected key finding 2"
  - "Expected key finding 3"
```

If you need to search internet for additional information, you may do so, but use this capability sparingly.

Please begin your response with your planning process, followed by the final YAML output enclosed within ```yaml``` tags.
"""

###########################################
### CODE GENERATOR AGENT PROMPTS ##########
###########################################

code_generator_system_df = """
You are an AI data analyst tasked with solving data analysis problems by generating executable Python code.
"""

code_generator_system_gen= """
You are an AI data analyst tasked with solving data analysis problems by generating executable Python code.
"""

code_generator_user_df_plan = """
Your objective is to implement the provided analysis plan using a pre-loaded pandas DataFrame named `df`. 

Here is the structured analysis plan or alternatively extra context if plan is not provided:

{}

To give you an idea of the data structure you'll be working with, here's a preview of the DataFrame:

{}

The following data model and helper functions are crucial for your implementation. Make sure to incorporate these fully in your solution:

{}

Now, let's look at the specific task you need to accomplish:

{}

Before we begin, here are the version specifications you need to adhere to:

{}

{}

{}

For additional context, here are the results from previous tasks:

{}

Your task is to provide a COMPLETE, EXECUTABLE PYTHON SCRIPT that fully implements the analysis plan.

Follow these key requirements:

1. Start with necessary import statements (pandas, numpy, plotly, etc.).
2. Perform specified data operations (segmentation, grouping, binning, aggregation).
3. Implement all analysis steps as outlined in the plan.
4. Create required visualizations using Plotly with fig.show() for display.
5. Generate the final output as specified, highlighting key insights.
6. Include print statements to display results.
7. Add brief comments to explain key code sections.
8. Use the pre-loaded DataFrame 'df' - do not include code to load data.
9. Incorporate and fully define all selected helper functions in your code.

Before generating the code, review and critique the provided analysis plan within <analysis_reflection> tags:

- Reflect on whether the proposed plan fully addresses the original task requirements
- Validate the key analysis steps and identify any gaps or missing elements
- Confirm the data operations align with the desired outcomes
- Verify the chosen visualizations effectively communicate the results
- Highlight any potential challenges or areas needing refinement

After your review, provide a complete Python script enclosed within ```python ``` tags. Your code should follow this general structure:

1. Import statements
2. Data comprehension (if needed)
3. Data operations
4. Analysis steps implementation
5. Visualizations
6. Final output generation

{}

Remember: Do not omit any code for brevity or ask the user to fill in missing parts. Ensure that all selected helper functions are fully defined and incorporated into your solution.
"""

code_generator_user_df_no_plan = """
Your objective is to solve the task provided by the user using a pre-loaded pandas DataFrame named `df`. 

{}

To give you an idea of the data structure you'll be working with, here's a preview of the DataFrame:

{}

The following data model and helper functions are crucial for your implementation. Make sure to incorporate these fully in your solution:

{}

Now, let's look at the specific task you need to accomplish:

{}

Before we begin, here are the version specifications you need to adhere to:

{}

{}

{}

For additional context, here are the results from previous tasks:

{}

Your job is to provide a COMPLETE, EXECUTABLE PYTHON SCRIPT that solves the given task. 

Follow these key requirements:

1. Start with necessary import statements (pandas, numpy, plotly, etc.).
2. Perform specified data operations (segmentation, grouping, binning, aggregation).
3. Implement all required analysis steps.
4. Create required visualizations using Plotly with fig.show() for display.
5. Generate the final output as specified, highlighting key insights.
6. Include print statements to display results.
7. Add brief comments to explain key code sections.
8. Use the pre-loaded DataFrame 'df' - do not include code to load data.
9. Incorporate and fully define all selected helper functions in your code.

Before generating the code, outline your analysis plan as a pseudo-code:

- Reflect on the objectives of the task and the proposed solution
- Validate the key analysis steps and identify any gaps or missing elements
- Confirm the data operations align with the desired outcomes
- Verify the chosen visualizations effectively communicate the results
- Highlight any potential challenges or areas needing refinement

After your reflection, provide a complete Python script enclosed within ```python ``` tags. Your code should follow this general structure:

1. Import statements
2. Data comprehension (if needed)
3. Data operations
4. Analysis steps implementation
5. Visualizations
6. Final output generation

{}

Remember: Do not omit any code for brevity or ask the user to fill in missing parts. Ensure that all selected helper functions are fully defined and incorporated into your solution.
"""

code_generator_user_gen_plan = """
You are an AI data analyst tasked with solving data analysis problems by generating executable Python code. Your goal is to implement the provided plan, which may involve data analysis, general coding tasks, or other programming challenges.

First, let's review the version specifications you need to adhere to:

{}

{}

{}

Now, let's examine the context and task at hand:

1. Structured analysis plan or additional context:

{}

2. Specific task to accomplish:

{}

3. Results from previous tasks (if any):

{}

4. Code example for reference:

{}

Before generating the code, please analyze the provided information and the task and translate the provided plan into a pseude code. Show your thought process inside <solution_planning> tags:

<solution_planning>
1. Review the analysis plan and task description:
   - Identify the main objectives
   - List the key steps required
   - Note any specific data operations or visualizations needed

2. Evaluate the version specifications:
   - Ensure compatibility with required libraries and their versions
   - Address any specific constraints or requirements

3. Consider the previous results and code example:
   - Determine how they relate to the current task
   - Identify any useful patterns or techniques to apply

4. Identify and list required libraries:
   - Based on the task and operations needed, list all necessary libraries
   - Note any specific version requirements

5. Outline the structure of your solution:
   - Plan the necessary import statements
   - Determine data loading or generation steps
   - List the main implementation steps
   - Plan output generation and visualization methods

6. Detail data analysis steps (if applicable):
   - Specify data cleaning and preprocessing steps
   - List required calculations or transformations
   - Outline any statistical analyses or machine learning tasks

7. Plan visualization approach (if applicable):
   - Determine appropriate chart types for the data and insights
   - List required Plotly functions and customizations

8. Identify potential challenges and solutions:
   - Address any gaps in the provided information
   - Propose solutions for potential issues
   - Consider edge cases and necessary error handling

9. Outline the final output format:
   - Specify how results will be presented (e.g., print statements, saved files)
   - Plan any summary statistics or key findings to highlight
</solution_planning>

Based on your analysis, please generate a complete, executable Python script that addresses all aspects of the provided plan. Your code should follow this general structure:

1. Import statements
2. Data loading or generation (if applicable)
3. Main implementation steps
4. Output generation
5. Visualizations (if applicable)

Key requirements for your code:
1. Start with necessary import statements for required libraries (e.g., pandas, numpy, plotly, requests).
2. Implement all steps as outlined in the plan.
3. For data analysis tasks:
   a. Include code to download (API, URL) or generate required data.
   b. Perform specified data operations (segmentation, grouping, binning, aggregation).
   c. Create required visualizations using Plotly with fig.show() for display.
4. For general coding tasks, implement the solution as specified in the plan.
5. Generate the final output as specified, highlighting key results or insights.
6. Include print statements to display intermediate and final results.
7. Add brief comments to explain key code sections.

Provide a COMPLETE, EXECUTABLE PYTHON SCRIPT enclosed within ```python ``` tags. Do not omit any code for brevity or ask the user to fill in missing parts.
"""

code_generator_user_gen_no_plan = """
You are an AI data analyst tasked with solving data analysis problems by generating executable Python code. Your goal is to implement the provided plan, which may involve data analysis, general coding tasks, or other programming challenges.

First, let's review the version specifications you need to adhere to:

{}

{}

{}

Now, let's examine the context and task at hand:

1. Specific task to accomplish:

{}

2. Results from previous tasks (if any):

{}

3. Code example for reference:

{}

Before generating the code, please analyze the provided information and the task and create a plan. Show your thought process inside <solution_planning> tags:

<solution_planning>
1. Review the analysis plan and task description:
   - Identify the main objectives
   - List the key steps required
   - Note any specific data operations or visualizations needed

2. Evaluate the version specifications:
   - Ensure compatibility with required libraries and their versions
   - Address any specific constraints or requirements

3. Consider the previous results and code example:
   - Determine how they relate to the current task
   - Identify any useful patterns or techniques to apply

4. Identify and list required libraries:
   - Based on the task and operations needed, list all necessary libraries
   - Note any specific version requirements

5. Outline the structure of your solution:
   - Plan the necessary import statements
   - Determine data loading or generation steps
   - List the main implementation steps
   - Plan output generation and visualization methods

6. Detail data analysis steps (if applicable):
   - Specify data cleaning and preprocessing steps
   - List required calculations or transformations
   - Outline any statistical analyses or machine learning tasks

7. Plan visualization approach (if applicable):
   - Determine appropriate chart types for the data and insights
   - List required Plotly functions and customizations

8. Identify potential challenges and solutions:
   - Address any gaps in the provided information
   - Propose solutions for potential issues
   - Consider edge cases and necessary error handling

9. Outline the final output format:
   - Specify how results will be presented (e.g., print statements, saved files)
   - Plan any summary statistics or key findings to highlight
</solution_planning>

Based on your analysis, please generate a complete, executable Python script that addresses all aspects of the provided plan. Your code should follow this general structure:

1. Import statements
2. Data loading or generation (if applicable)
3. Main implementation steps
4. Output generation
5. Visualizations (if applicable)

Key requirements for your code:
1. Start with necessary import statements for required libraries (e.g., pandas, numpy, plotly, requests).
2. Implement all steps as outlined in the plan.
3. For data analysis tasks:
   a. Include code to download (API, URL) or generate required data.
   b. Perform specified data operations (segmentation, grouping, binning, aggregation).
   c. Create required visualizations using Plotly with fig.show() for display.
4. For general coding tasks, implement the solution as specified in the plan.
5. Generate the final output as specified, highlighting key results or insights.
6. Include print statements to display intermediate and final results.
7. Add brief comments to explain key code sections.

Provide a COMPLETE, EXECUTABLE PYTHON SCRIPT enclosed within ```python ``` tags. Do not omit any code for brevity or ask the user to fill in missing parts.
"""

###########################################
### ERROR CORRECTOR AGENT PROMPTS #########
###########################################

error_corector_system = """
The execution of the code that you provided in the previous step resulted in an error.

Here is the error message:
<error_message>
{}
</error_message>

1. Explain the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
2. Explain the fix or changes needed to correct the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
3. Return a complete, corrected python code that incorporates the fixes for the error.

Make sure the corrected code is compatible with the following versions:
Python version: 
<python_version>
{}
</python_version>

Pandas version:
<pandas_version>
{}
</pandas_version>

Plotly version:
<plotly_version>
{}
</plotly_version>

Always include the import statements at the top of the code, and comments and print statements where necessary.
Do not omit any code for brevity, or ask the user to fill in missing parts!
"""

error_corector_edited_system = """
The user manually edited the code you provided in the previous step, but its execution resulted in an error.

Here is the edited code:
<edited_code>
{}
</edited_code>

Here is the error message:
<error_message>
{}
</error_message>

1. Explain the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
2. Explain the fix or changes needed to correct the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
3. Return a complete, corrected python code that incorporates the fixes for the error.

Make sure the corrected code is compatible with the following versions:
Python version: 
<python_version>
{}
</python_version>

Pandas version:
<pandas_version>
{}
</pandas_version>

Plotly version:
<plotly_version>
{}
</plotly_version>

Always include the import statements at the top of the code, and comments and print statements where necessary.
Do not omit any code for brevity, or ask the user to fill in missing parts!
"""

error_corector_system_reasoning = """
The execution of the code that you provided in the previous step resulted in an error.

Here is the error message:

ERROR MESSAGE:

{}

1. Explain the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
2. Explain the fix or changes needed to correct the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
3. Return a complete, corrected python code that incorporates the fixes for the error.

Make sure the corrected code is compatible with the following versions:

PYTHON VERSION:

{}

PANDAS VERSION:

{}

PLOTLY VERSION:

{}

Always include the import statements at the top of the code, and comments and print statements where necessary.
Do not omit any code for brevity, or ask the user to fill in missing parts!
"""

error_corector_edited_system_reasoning = """
The user manually edited the code you provided in the previous step, but its execution resulted in an error.

Here is the edited code:

EDITED CODE:

{}

Here is the error message:

ERROR MESSAGE:

{}

1. Explain the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
2. Explain the fix or changes needed to correct the error in a conceptual manner, without delving into the code syntax. Remember to not include code snippets in your explanation!
3. Return a complete, corrected python code that incorporates the fixes for the error.

Make sure the corrected code is compatible with the following versions:

PYTHON VERSION:

{}

PANDAS VERSION:

{}

PLOTLY VERSION:

{}

Always include the import statements at the top of the code, and comments and print statements where necessary.
Do not omit any code for brevity, or ask the user to fill in missing parts!
"""

###########################################
### PLAN REVIEWER AGENT PROMPTS ###########
###########################################

reviewer_system = """
As an AI QA Engineer, your role is to evaluate whether the the plan closely matches the code execution and the task requirements.

Code:
{}

Plan:
{}

First: Provide a brief summary of your evaluation.
Second: Modify the original plan maintaining its original structure, but incorporating any necessary changes based on the code execution.
Third: Enclose the modified plan within ```yaml tags. IMPORTANT

Example Output:
Evaluation Summary:
<Your summary here>

Modified Plan:
```yaml
<Your modified plan here>
```
"""
###########################################
### SUMMARIZER AGENT PROMPTS ##############
###########################################

solution_summarizer_system = """
The user presented you with the following task.
Task: {}

To address this, you have designed an algorithm.
Algorithm: {}.

You have crafted a Python code based on this algorithm, and the output generated by the code's execution is as follows.
Output: {}.

Please provide a summary of insights achieved through your method's implementation.
Present this information in a well-structured format, using tables for data organization, LaTeX for mathematical expressions, and strategically placed bullet points for clarity. 
Ensure that all results from the computations are included in your summary.
If the user asked for a particular information that is not included in the code execution results, and you know the answer please incorporate the answer to your summary.
"""

solution_summarizer_custom_code_system = """
The user edited the code you provided in one of the the previous step, and its execution resulted in the following output.

Custom code crafted by the user:

{}

Output: 

{}

Please provide a summary of insights achieved through the user's custom code implementation.
Present this information in a well-structured format, using tables for data organization, LaTeX for mathematical expressions, and strategically placed bullet points for clarity.
Ensure that all results from the computations are included in your summary.
"""

###########################################
### GOOGLE SEARCH AGENT PROMPTS ###########
###########################################

google_search_query_generator_system = """
You are an AI internet research specialist and your job is to formulate a user's question as a search query.
Reframe the user's question into a search query as per the below examples.

Example input: Can you please find out what is the popularity of Python programming language in 2023?
Example output: Popularity of Python programming language in 2023

The user asked the following question: '{}'.
"""
# Google Search Summarizer Agent Prompts
google_search_summarizer_system = """
Read the following text carefully to understand its content. 
 
Text:

{}

Based on your understanding, provide a clear and comprehensible answer to the question below by extracting relevant information from the text.
Be certain to incorporate all relevant facts and insights.
Fill in any information that user has asked for, and that is missing from the text.

Question: {}
"""
google_search_react_system = """
You are an Internet Research Specialist, and run in a loop of Thought, Action, Observation. This Thought, Action, Observation loop is repeated until you output an Answer.
At the end of the loop you output an Answer.
Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you.
Observation will be the result of running those actions.

Your available actions are:

calculate:
e.g. calculate: 4 * 7 / 3
Runs a calculation and returns the number - uses Python so be sure to use floating point syntax if necessary

google_search:
e.g. google_search: Popularity of the Python programming language in 2022
Returns a summary of a Google Search
Today's Date is: {}

Use Google Search ONLY if you dont know the answer to the question!

Example session:

Question: What is Leonardo di Caprio's girlfriends age raised to the power of 2?\n
Thought: I need to search for Leonardo DiCaprio's girlfriend's name.\n
Action: google_search: Leonardo DiCaprio's girlfriend's name\n

You will be called again with this:

Observation: Leonardo DiCaprio has had a string of high-profile relationships over the years, including with models Gisele Bündchen, Bar Refaeli, and Nina Agdal. As of 2023, he is currently dating actress and model Camila Morrone.

You then output:

Thought: Camila Morrone's age.
Action: google_search: Camila Morrone's age

You will be called again with this:

Observation: Camila Morrone is 23 years old.

You then output:

Thought: Camila Morrone is 23 years old. I need to raise 23 to the power of 2.
Action: calculate: 23**2

You will be called again with this:

Observation: 529

You then output the finall answer:

Answer: Leonardo's current girlfriend is Camila Morrone, who is 23 years old. 23 raised to the power of 2 is 529.
"""

###########################################
### PLOT QUERY AGENT PROMPTS ##############
###########################################

plot_query="""
Examine and explain the following visualization(s) in detail. Your response should illuminate what the data shows, its significance, and the principles behind its visual representation. Consider patterns, trends, relationships, and any noteworthy features that deserve attention.

{}

In your response:

Describe what the visualization represents and its key elements
Highlight meaningful patterns and relationships in the data
Explain the reasoning behind the visualization choices
Point out any subtle but important details
Share relevant theoretical context about this type of visualization

Provide your insights in clear, accessible language. Do not include code or technical implementation details unless specifically requested.
"""

plot_query_routing = """
This query relates to a data visualization, plot, or chart.
Routing instructions:
- Default: Route to Research Specialist for interpretation, explanation, and analysis
- Exception: Route to Data Analyst ONLY if both conditions are met:
  1. User explicitly requests modifications or corrections to the visualization
  2. Task requires technical implementation changes

Task:
{}
"""

