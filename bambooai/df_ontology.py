ontology = """
@prefix : <http://www.semanticweb.org/esc/ontologies/2024/5/etm_2/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xml: <http://www.w3.org/XML/1998/namespace> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@base <http://www.semanticweb.org/esc/ontologies/2024/5/etm_2/> .

###########################################################################################
# THIS IS A SAMPLE ONTOLOGY DESCRIBING THE DATAFRAME STRUCTURE FOR A CUSTOM FITNESS DATASET
# DEVELOPED USING PROTEGE (https://protege.stanford.edu/)
###########################################################################################

#    Object Properties

:derivedFrom rdf:type owl:ObjectProperty ;
             rdfs:domain :Derived ;
             rdfs:range :DirectlyMeasured ,
                        :PreComputed .

:preComputedFrom rdf:type owl:ObjectProperty ;
                 rdfs:domain :PreComputed ;
                 rdfs:range :DirectlyMeasured ,
                            :PreComputed .

:canBeComputedUsingFunction rdf:type owl:ObjectProperty ;
                            rdfs:domain :DataObjects ;
                            rdfs:range :Function .

:functionRequiresMeasurements rdf:type owl:ObjectProperty ;
                              rdfs:domain :Function ;
                              rdfs:range :MetricCategory .

:hasRelation rdf:type owl:ObjectProperty ;
             rdfs:domain :Key ,
                         :MetricCategory ;
             rdfs:range :Key .

#    Data properties

:derivedUsingFormula rdf:type owl:DatatypeProperty ;
                     rdfs:domain :MetricCategory ;
                     rdfs:range xsd:string .

:isPresentInDataset rdf:type owl:DatatypeProperty ;
                    rdfs:domain :Key ,
                                :MetricCategory ;
                    rdfs:range xsd:boolean .

:recordedWithFrequency rdf:type owl:DatatypeProperty ;
                       rdfs:domain :MetricCategory ;
                       rdfs:range xsd:string .

:functionDefinition rdf:type owl:DatatypeProperty ;
                    rdfs:domain :Function ;
                    rdfs:range xsd:string .

:measuredInUnits rdf:type owl:DatatypeProperty ;
                 rdfs:domain :MetricCategory ;
                 rdfs:range xsd:string .

#    Classes

:Dataframe rdf:type owl:Class ;
           rdfs:subClassOf :DataObjects .

:Derived rdf:type owl:Class ;
         rdfs:subClassOf :MetricType .

:DirectlyMeasured rdf:type owl:Class ;
                  rdfs:subClassOf :MetricType .

:MetricType rdf:type owl:Class .

:PreComputed rdf:type owl:Class ;
             rdfs:subClassOf :MetricType .

:Scalar rdf:type owl:Class ;
        rdfs:subClassOf :DataObjects .

:Velocity rdf:type owl:Class ;
          rdfs:subClassOf :MetricCategory .

:DataObjects rdf:type owl:Class .

:Dictionary rdf:type owl:Class ;
            rdfs:subClassOf :DataObjects .

:Environmental rdf:type owl:Class ;
               rdfs:subClassOf :MetricCategory .

:Function rdf:type owl:Class .

:Geospatial rdf:type owl:Class ;
            rdfs:subClassOf :MetricCategory .

:Key rdf:type owl:Class .

:List rdf:type owl:Class ;
      rdfs:subClassOf :DataObjects .

:Mechanical rdf:type owl:Class ;
            rdfs:subClassOf :MetricCategory .

:Metabolic rdf:type owl:Class ;
           rdfs:subClassOf :MetricCategory .

:MetricCategory rdf:type owl:Class .

:Temporal rdf:type owl:Class ;
          rdfs:subClassOf :MetricCategory .

#    Individuals

:AthleteID rdf:type owl:NamedIndividual ,
                    :Key ;
           :isPresentInDataset "true"^^xsd:boolean .

:DistanceSegments rdf:type owl:NamedIndividual ,
                        :Dataframe ;
               :canBeComputedUsingFunction :ditanceSegmentsFunction .

:Pace rdf:type owl:NamedIndividual ,
               :Derived ,
               :Velocity ;
      :derivedFrom :Speed ;
      :hasRelation :ActivityID ,
                   :ActivityType ,
                   :Datetime ,
                   :LapID ;
      :derivedUsingFormula "pace_min_per_km = 1000 / (Speed * 60)" ;
      :isPresentInDataset "false"^^xsd:boolean ;
      :recordedWithFrequency "10 Seconds" ;
      :measuredInUnits "Minutes per Kilometer" .

:TimeSegments rdf:type owl:NamedIndividual ,
                    :Dataframe ;
           :canBeComputedUsingFunction :timeSegmentsFunction .

:Torque rdf:type owl:NamedIndividual ,
                 :Derived ,
                 :Mechanical ;
        :derivedFrom :Cadence ,
                     :Power ;
        :hasRelation :ActivityID ,
                     :ActivityType ,
                     :Datetime ,
                     :LapID ;
        :derivedUsingFormula \"\"\"# Calculate torque
import numpy as np
Torque = Power * 60 / (2 * np.pi * Cadence)\"\"\" ;
        :isPresentInDataset "false"^^xsd:boolean ;
        :recordedWithFrequency "10 Seconds" ;
        :measuredInUnits "Nm (Newton Meters)" .

:ditanceSegmentsFunction rdf:type owl:NamedIndividual ,
                                :Function ;
                       :functionRequiresMeasurements :Distance ;
                       :functionDefinition \"\"\"Create distance-based segments and calculate cumulative distance within each activity.
    
Parameters:
    df (pandas.DataFrame): The input DataFrame
    activity_col (str): Name of the activity ID column (default: 'ActivityID')
    distance_col (str): Name of the distance column (default: 'Distance')
    segment_distance (float): Distance in meters for each segment (default: 1000, which is 1km)
    
Returns:
    pandas.DataFrame: DataFrame with additional columns for cumulative distance, segment, and distance within segment

Abstract_Syntax:
    # Sort the DataFrame by ActivityID and Datetime 
    df = df.sort_values(by=[activity_col, 'Datetime'])
    
    # Group by ActivityID and process each group
    def process_group(group):
        # Calculate cumulative distance within the activity
        group['cumulative_distance'] = group[distance_col].cumsum()
        
        # Create segments based on cumulative distance
        group['segment'] = (group['cumulative_distance'] // segment_distance).astype(int)
        
        return group

    # Apply the processing function to each activity group
    df = df.groupby(activity_col, group_keys=False).apply(process_group)\"\"\" .

:timeSegmentsFunction rdf:type owl:NamedIndividual ,
                            :Function ;
                   :functionRequiresMeasurements :Datetime ;
                   :functionDefinition \"\"\"Calculate time delta and create time segments for data recorded at 10-second intervals, grouped by ActivityID.
    
Parameters:
    df (pandas.DataFrame): The input DataFrame
    datetime_col (str): Name of the datetime column (default: 'Datetime')
    activity_col (str): Name of the activity ID column (default: 'ActivityID')
    segment_seconds (int): Time interval in seconds for segmentation (default: 1200, which is 20 minutes)
    
Returns:
    pandas.DataFrame: DataFrame with additional columns for time delta and segment

Abstract Syntax:
    # Ensure the datetime column is in datetime format
    df[datetime_column] = pd.to_datetime(df[datetime_column])
    
    # Sort the DataFrame by ActivityID and Datetime
    df = df.sort_values(by=[activity_col, datetime_col])
    
    # Group by ActivityID and calculate time delta and segments
    def process_group(group):
        group['time_delta'] = group[datetime_col].diff()

        expected_delta = pd.Timedelta(seconds=10)
        is_consistent = (group['time_delta'].dropna() == expected_delta).all()
        
        if not is_consistent:
            print(f\"Warning: Data for ActivityID is not consistently recorded at 10-second intervals.\")

        group['segment'] = ((group[datetime_col] - group[datetime_col].min()).dt.total_seconds() // segment_seconds).astype(int)
        
        return group

    # Apply the processing function to each activity group
    df = df.groupby(activity_col, group_keys=False).apply(process_group)\"\"\" .

:ActivityID rdf:type owl:NamedIndividual ,
                     :Key ;
            :hasRelation :AthleteID ;
            :isPresentInDataset "true"^^xsd:boolean .

:ActivityType rdf:type owl:NamedIndividual ,
                       :Key ;
              :hasRelation :ActivityID ;
              :isPresentInDataset "true"^^xsd:boolean .

:AirTemperature rdf:type owl:NamedIndividual ,
                         :DirectlyMeasured ,
                         :Environmental ;
                :hasRelation :ActivityID ,
                             :ActivityType ,
                             :Datetime ,
                             :LapID ;
                :isPresentInDataset "true"^^xsd:boolean ;
                :recordedWithFrequency "10 Seconds" ;
                :measuredInUnits "Celsius" .

:Cadence rdf:type owl:NamedIndividual ,
                  :DirectlyMeasured ,
                  :Mechanical ;
         :hasRelation :ActivityID ,
                      :ActivityType ,
                      :Datetime ,
                      :LapID ;
         :isPresentInDataset "true"^^xsd:boolean ;
         :recordedWithFrequency "10 Seconds" ;
         :measuredInUnits "RPM" .

:Datetime rdf:type owl:NamedIndividual ,
                   :DirectlyMeasured ,
                   :Key ,
                   :Temporal ;
          :hasRelation :ActivityID ,
                       :ActivityType ,
                       :LapID ;
          :isPresentInDataset "true"^^xsd:boolean ;
          :recordedWithFrequency "10 Seconds" ;
          :measuredInUnits "ISO 8601" .

:Distance rdf:type owl:NamedIndividual ,
                   :PreComputed ,
                   :Geospatial ;
          :preComputedFrom :Latitude ,
                           :Longitude ;
          :hasRelation :ActivityID ,
                       :ActivityType ,
                       :Datetime ,
                       :LapID ;
          :isPresentInDataset "true"^^xsd:boolean ;
          :recordedWithFrequency "10 Seconds" ;
          :measuredInUnits "Meters" .

:Elevation rdf:type owl:NamedIndividual ,
                    :DirectlyMeasured ,
                    :Geospatial ;
           :hasRelation :ActivityID ,
                        :ActivityType ,
                        :Datetime ,
                        :LapID ;
           :isPresentInDataset "true"^^xsd:boolean ;
           :recordedWithFrequency "10 Seconds" ;
           :measuredInUnits "Meters" .

:Gradient rdf:type owl:NamedIndividual ,
                   :PreComputed ,
                   :Geospatial ;
          :preComputedFrom :Distance ,
                           :Elevation ;
          :hasRelation :ActivityID ,
                       :ActivityType ,
                       :Datetime ,
                       :LapID ;
          :isPresentInDataset "true"^^xsd:boolean ;
          :recordedWithFrequency "10 Seconds" ;
          :measuredInUnits "Percent" ;
          rdfs:comment "Ratio of the vertical gain to the horizontal distance covered, expressed as a percentage" .

:Heartrate rdf:type owl:NamedIndividual ,
                    :DirectlyMeasured ,
                    :Metabolic ;
           :hasRelation :ActivityID ,
                        :ActivityType ,
                        :Datetime ,
                        :LapID ;
           :isPresentInDataset "true"^^xsd:boolean ;
           :recordedWithFrequency "10 Seconds" ;
           :measuredInUnits "BPM" .

:Humidity rdf:type owl:NamedIndividual ,
                   :DirectlyMeasured ,
                   :Environmental ;
          :hasRelation :ActivityID ,
                       :ActivityType ,
                       :Datetime ,
                       :LapID ;
          :isPresentInDataset "false"^^xsd:boolean ;
          :recordedWithFrequency "10 Seconds" ;
          :measuredInUnits "Percent" .

:LapID rdf:type owl:NamedIndividual ,
                :Key ;
       :hasRelation :ActivityID ;
       :isPresentInDataset "true"^^xsd:boolean .

:Latitude rdf:type owl:NamedIndividual ,
                   :DirectlyMeasured ,
                   :Geospatial ;
          :hasRelation :ActivityID ,
                       :ActivityType ,
                       :Datetime ,
                       :LapID ;
          :isPresentInDataset "true"^^xsd:boolean ;
          :recordedWithFrequency "10 Seconds" ;
          :measuredInUnits "Degrees" .

:Longitude rdf:type owl:NamedIndividual ,
                    :DirectlyMeasured ,
                    :Geospatial ;
           :hasRelation :ActivityID ,
                        :ActivityType ,
                        :Datetime ,
                        :LapID ;
           :isPresentInDataset "true"^^xsd:boolean ;
           :recordedWithFrequency "10 Seconds" ;
           :measuredInUnits "Degrees" .

:Power rdf:type owl:NamedIndividual ,
                :DirectlyMeasured ,
                :Mechanical ;
       :hasRelation :ActivityID ,
                    :ActivityType ,
                    :Datetime ,
                    :LapID ;
       :isPresentInDataset "true"^^xsd:boolean ;
       :recordedWithFrequency "10 Seconds" ;
       :measuredInUnits "Watts" .

:Speed rdf:type owl:NamedIndividual ,
                :PreComputed ,
                :Velocity ;
       :preComputedFrom :Datetime ,
                        :Distance ;
       :hasRelation :ActivityID ,
                    :ActivityType ,
                    :Datetime ,
                    :LapID ;
       :isPresentInDataset "true"^^xsd:boolean ;
       :recordedWithFrequency "10 Seconds" ;
       :measuredInUnits "Meters per Second" .

:WindDirection rdf:type owl:NamedIndividual ,
                        :DirectlyMeasured ,
                        :Environmental ;
               :hasRelation :ActivityID ,
                            :ActivityType ,
                            :Datetime ,
                            :LapID ;
               :isPresentInDataset "false"^^xsd:boolean ;
               :recordedWithFrequency "10 Seconds" ;
               :measuredInUnits "Degrees" .

:WindSpeed rdf:type owl:NamedIndividual ,
                    :DirectlyMeasured ,
                    :Environmental ;
           :hasRelation :ActivityID ,
                        :ActivityType ,
                        :Datetime ,
                        :LapID ;
           :isPresentInDataset "false"^^xsd:boolean ;
           :recordedWithFrequency "10 Seconds" ;
           :measuredInUnits "Meters per second" .

:meanMaxCurve rdf:type owl:NamedIndividual ,
                       :List ;
              :canBeComputedUsingFunction :meanMaxCurveFunction .

:meanMaxCurveFunction rdf:type owl:NamedIndividual ,
                               :Function ;
                      :functionRequiresMeasurements :Power ;
                      :functionDefinition \"\"\"Calculate the maximum rolling mean for a measurement and various window sizes.

Parameters:
    df (pd.DataFrame): DataFrame containing the data
    measurement (str): Column name of the measurement
    windows (list of int): List of window sizes

Returns:
    list of float: Maximum rolling mean values for each window size

Abstract Syntax:
    windows = [1,3,6,18,30,60,120,240,360]
    mean_maximal_powers = []
    for window in windows:
        rolling_mean = df[measurement].rolling(window=window).mean()
        max_rolling_mean = rolling_mean.max()
        mean_maximal_powers.append(max_rolling_mean)\"\"\" .
"""
