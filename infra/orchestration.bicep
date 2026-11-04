targetScope = 'resourceGroup'
// Second phase after SQL bootstrap, explicit approval, and identity/network tests.
param factoryName string
param storageAccountName string
param synapseWorkspaceName string
param dedicatedPoolName string = 'retail'
param historicalDate string = '2010-12-01'
param sourceSha256 string = 'UNCONFIGURED'
@description('UTC first schedule time. Trigger is deployed STOPPED; starting is separate approval.')
param scheduleStartTime string = '2030-01-01T00:00:00Z'

resource factory 'Microsoft.DataFactory/factories@2018-06-01' existing = { name: factoryName }
resource lake 'Microsoft.DataFactory/factories/linkedservices@2018-06-01' = {
  parent: factory
  name: 'RetailLakeManagedIdentity'
  properties: { type: 'AzureBlobFS', typeProperties: { url: 'https://${storageAccountName}.dfs.${az.environment().suffixes.storage}' } }
}
resource warehouse 'Microsoft.DataFactory/factories/linkedservices@2018-06-01' = {
  parent: factory
  name: 'RetailDedicatedPoolManagedIdentity'
  properties: { type: 'AzureSqlDW', typeProperties: {
    server: '${synapseWorkspaceName}.sql.azuresynapse.net'
    database: dedicatedPoolName
    encrypt: 'mandatory'
    trustServerCertificate: false
    authenticationType: 'SystemAssignedManagedIdentity'
  } }
}
resource manifest 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: factory
  name: 'ReadyManifest'
  properties: {
    type: 'Json'
    linkedServiceName: { type: 'LinkedServiceReference', referenceName: lake.name }
    parameters: { sourceSha256: { type: 'String' }, businessDate: { type: 'String' } }
    typeProperties: { location: { type: 'AzureBlobFSLocation', fileSystem: 'batches'
      folderPath: { type: 'Expression', value: '@concat(\'ready/retail-synapse-v1/\',dataset().sourceSha256)' }
      fileName: { type: 'Expression', value: '@concat(dataset().businessDate,\'.json\')' }
    } }
  }
}
resource batch 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: factory
  name: 'PreparedDailyParquet'
  properties: {
    type: 'Parquet'
    linkedServiceName: { type: 'LinkedServiceReference', referenceName: lake.name }
    parameters: { sourceSha256: { type: 'String' }, businessDate: { type: 'String' } }
    typeProperties: { location: { type: 'AzureBlobFSLocation', fileSystem: 'batches'
      folderPath: { type: 'Expression', value: '@concat(\'prepared/retail-synapse-v1/\',dataset().sourceSha256)' }
      fileName: { type: 'Expression', value: '@concat(dataset().businessDate,\'.parquet\')' }
    } }
  }
}
resource stage 'Microsoft.DataFactory/factories/datasets@2018-06-01' = {
  parent: factory
  name: 'StageInvoiceLines'
  properties: {
    type: 'AzureSqlDWTable'
    linkedServiceName: { type: 'LinkedServiceReference', referenceName: warehouse.name }
    typeProperties: { schema: 'retail', table: 'stage_lines' }
  }
}
resource publish 'Microsoft.DataFactory/factories/pipelines@2018-06-01' = {
  parent: factory
  name: 'PublishRetailDate'
  properties: loadJsonContent('../azure/adf/publish-date.json')
  dependsOn: [manifest, batch, stage]
}
resource daily 'Microsoft.DataFactory/factories/triggers@2018-06-01' = {
  parent: factory
  name: 'HistoricalDailyLab'
  properties: {
    type: 'ScheduleTrigger'
    description: 'Repeated historical-date lab trigger; not a current retail feed. Advance date explicitly for backfills.'
    typeProperties: { recurrence: { frequency: 'Day', interval: 1, startTime: scheduleStartTime, timeZone: 'UTC' } }
    pipelines: [{ pipelineReference: { type: 'PipelineReference', referenceName: publish.name }
      parameters: { businessDate: historicalDate, sourceSha256: sourceSha256, allowRevision: false }
    }]
  }
}
