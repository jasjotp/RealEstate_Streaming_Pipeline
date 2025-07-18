import logging 
from cassandra.cluster import Cluster
from pyspark.sql import SparkSession 
from pyspark.sql.types import StructType, StructField, StringType, ArrayType
from pyspark.sql.functions import from_json, col 

# function to create key space in Cassandra 
def create_keyspace(session):
    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS property_streams
        WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'}
    """)
    print('Keyspace created successfully...')

# function to create table for property details 
def create_table(session):
    session.execute("""
        CREATE TABLE IF NOT EXISTS property_streams.properties (
            address text, 
            price text,
            description text,
            beds text,
            baths text,
            sqft text,
            link text,
            pictures list<text>,
            receptions text,
            epc_rating text,
            tenure text,
            time_remaining_on_lease text,
            service_charge text,
            council_tax_band text,
            ground_rent text,
            floorplanimage text,
            PRIMARY KEY (link)
        );
    """)

    print('Table created successully...')

# function to insert data into Cassandra 
def insert_data(session, **kwargs):
    print('Inserting data into Cassandra')
    session.execute("""
        INSERT INTO property_streams.properties(
            address, 
            price, 
            description, 
            beds, 
            baths, 
            sqft, 
            link, 
            pictures, 
            receptions, 
            epc_rating, 
            tenure, 
            time_remaining_on_lease, 
            service_charge, 
            council_tax_band, 
            ground_rent, 
            floorplanimage
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)            
    """, (
        kwargs.get('address'),
        kwargs.get('price'),
        kwargs.get('description'),
        kwargs.get('beds'),
        kwargs.get('baths'),
        kwargs.get('sqft'),
        kwargs.get('link'),
        kwargs.get('pictures'),  # list[str]
        kwargs.get('receptions'),
        kwargs.get('epc_rating'),
        kwargs.get('tenure'),
        kwargs.get('time_remaining_on_lease'),
        kwargs.get('service_charge'),
        kwargs.get('council_tax_band'),
        kwargs.get('ground_rent'),
        kwargs.get('floorplanimage')
    ))

    print('Data inserted into Cassandra successfully')

# function to initiailize Cassandra session 
def create_cassandra_session():
    session = Cluster(['cassandra']).connect()

    if session is not None: 
        # create a keyspace 
        create_keyspace(session)

        # create a table 
        create_table(session)

    return session 

def main():
    # connect to Kafka 
    logging.basicConfig(level = logging.INFO)
    spark = (SparkSession.builder.appName('RealEstateSparkConsumer')
            .config('spark.cassandra.connection.host', 'localhost')
            .config('spark.jars.packages', 'com.datastax.spark:spark-cassandra-connector_2.12:3.4.1,org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.1')
            .config("spark.sql.streaming.checkpointLocation", "file:///home/jasjotparmar/spark-checkpoints")
            .getOrCreate()
            )
    
    kafka_df = (spark.readStream.format('kafka')
                .option('kafka.bootstrap.servers', 'kafka-broker:29092')
                .option('subscribe', 'properties')
                .option('startingOffsets', 'earliest') # start reading from the beginning of the Kafka topic, even if the messages were published before the Spark job started
                .option("failOnDataLoss", "false")
                .load()
            )
    
    # define the schema structure 
    schema = StructType([
        StructField("Address", StringType(), True),
        StructField("Price", StringType(), True),
        StructField("Description", StringType(), True),
        StructField("Beds", StringType(), True),
        StructField("Baths", StringType(), True),
        StructField("SqFt", StringType(), True),
        StructField("Link", StringType(), True),
        StructField("Pictures", ArrayType(StringType()), True),
        StructField("Receptions", StringType(), True),
        StructField("EPC Rating", StringType(), True),
        StructField("Tenure", StringType(), True),
        StructField("Time Remaining on Lease", StringType(), True),
        StructField("Service Charge", StringType(), True),
        StructField("Council Tax Band", StringType(), True),
        StructField("Ground Rent", StringType(), True),
        StructField("FloorPlanImage", StringType(), True)
    ])

    kafka_df = (kafka_df.selectExpr("CAST(value AS STRING) as value")
    .select(from_json(col("value"), schema).alias('data'))
    .select('data.*')
    )

    # rename the columns in the df to lowercase to be compatible with cassandra for ease of use downstream 
    kafka_df = kafka_df.withColumnRenamed("Address", "address") \
                   .withColumnRenamed("Price", "price") \
                   .withColumnRenamed("Description", "description") \
                   .withColumnRenamed("Beds", "beds") \
                   .withColumnRenamed("Baths", "baths") \
                   .withColumnRenamed("SqFt", "sqft") \
                   .withColumnRenamed("Link", "link") \
                   .withColumnRenamed("Pictures", "pictures") \
                   .withColumnRenamed("Receptions", "receptions") \
                   .withColumnRenamed("EPC Rating", "epc_rating") \
                   .withColumnRenamed("Tenure", "tenure") \
                   .withColumnRenamed("Time Remaining on Lease", "time_remaining_on_lease") \
                   .withColumnRenamed("Service Charge", "service_charge") \
                   .withColumnRenamed("Council Tax Band", "council_tax_band") \
                   .withColumnRenamed("Ground Rent", "ground_rent") \
                   .withColumnRenamed("FloorPlanImage", "floorplanimage")

    # write the data to Cassandra  
    cassandra_query = (kafka_df.writeStream
                       .option("checkpointLocation", "/tmp/spark-checkpoints")
                       .foreachBatch(lambda batch_df, batch_id: batch_df.foreach(
                           lambda row: insert_data(create_cassandra_session(), **row.asDict()))) # write each batch to Cassandra
                        .start()
                        .awaitTermination()
                       )

if __name__ == '__main__':
    main()