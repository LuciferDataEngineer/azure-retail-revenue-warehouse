targetScope = 'resourceGroup'

@description('No resources are created unless approved deployment explicitly sets this true.')
param deployLab bool = false
@allowed(['dev'])
param environment string = 'dev'
param location string = 'australiaeast'
@minLength(3)
@maxLength(10)
param prefix string = 'retaillab'
@description('Existing approved Microsoft Entra admin group. Never use a source-code credential.')
param entraAdminObjectId string = '00000000-0000-0000-0000-000000000000'
param entraAdminName string = 'UNCONFIGURED'
@description('Dedicated SQL pool compute incurs charges; separate explicit opt-in after approval.')
param deployDedicatedPool bool = false
@description('Create the producer job only after its reviewed image is published.')
param deployProducer bool = false
param producerImage string = 'UNCONFIGURED'
param alertActionGroupId string = ''

var suffix = uniqueString(resourceGroup().id, prefix)
var tags = { project: 'retail-revenue-warehouse', environment: environment, lifecycle: 'portfolio-lab' }
var blobReader = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1')
var blobContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')

resource lake 'Microsoft.Storage/storageAccounts@2023-05-01' = if (deployLab) {
  name: '${prefix}${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Enabled' // authenticated public-endpoint lab; prod contract is blocked.
    networkAcls: { bypass: 'None', defaultAction: 'Allow' }
  }
}
resource blob 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = if (deployLab) {
  parent: lake
  name: 'default'
  properties: { containerDeleteRetentionPolicy: { enabled: true, days: 7 } }
}
resource raw 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deployLab) {
  parent: blob
  name: 'raw'
  properties: { publicAccess: 'None' }
}
resource batches 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deployLab) {
  parent: blob
  name: 'batches'
  properties: { publicAccess: 'None' }
}
resource workspaceFiles 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deployLab) {
  parent: blob
  name: 'workspace'
  properties: { publicAccess: 'None' }
}
resource factory 'Microsoft.DataFactory/factories@2018-06-01' = if (deployLab) {
  name: '${prefix}-adf-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: { publicNetworkAccess: 'Enabled' }
}
resource synapse 'Microsoft.Synapse/workspaces@2021-06-01' = if (deployLab) {
  name: '${prefix}-syn-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    defaultDataLakeStorage: { accountUrl: 'https://${lake.name}.dfs.${az.environment().suffixes.storage}', filesystem: workspaceFiles.name }
    azureADOnlyAuthentication: true
    publicNetworkAccess: 'Enabled'
    trustedServiceBypassEnabled: false
  }
}
resource entraAdmin 'Microsoft.Synapse/workspaces/administrators@2021-06-01' = if (deployLab) {
  parent: synapse
  name: 'activeDirectory'
  properties: { administratorType: 'ActiveDirectory', login: entraAdminName, sid: entraAdminObjectId, tenantId: tenant().tenantId }
}
resource pool 'Microsoft.Synapse/workspaces/sqlPools@2021-06-01' = if (deployLab && deployDedicatedPool) {
  parent: synapse
  name: 'retail'
  location: location
  tags: tags
  sku: { name: 'DW100c' }
  properties: { createMode: 'Default', collation: 'Latin1_General_100_BIN2' }
}
resource adfRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployLab) {
  scope: batches
  name: guid(batches.id, factory.id, blobReader)
  properties: { roleDefinitionId: blobReader, principalId: factory!.identity.principalId, principalType: 'ServicePrincipal' }
}
resource synapseRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployLab) {
  scope: batches
  name: guid(batches.id, synapse.id, blobReader)
  properties: { roleDefinitionId: blobReader, principalId: synapse!.identity.principalId, principalType: 'ServicePrincipal' }
}
resource synapseWorkspace 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployLab) {
  scope: workspaceFiles
  name: guid(workspaceFiles.id, synapse.id, blobContributor)
  properties: { roleDefinitionId: blobContributor, principalId: synapse!.identity.principalId, principalType: 'ServicePrincipal' }
}
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (deployLab) {
  name: '${prefix}-logs-${suffix}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30, workspaceCapping: { dailyQuotaGb: 1 } }
}
resource producerEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = if (deployLab && deployProducer) {
  name: '${prefix}-jobs-${suffix}'
  location: location
  tags: tags
  properties: { appLogsConfiguration: { destination: 'azure-monitor' } }
}
resource producer 'Microsoft.App/jobs@2024-03-01' = if (deployLab && deployProducer) {
  name: '${prefix}-producer-${suffix}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    environmentId: producerEnvironment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
    }
    template: { containers: [{
      name: 'producer'
      image: producerImage
      resources: { cpu: 1, memory: '2Gi' }
      env: [{ name: 'RETAIL_STORAGE_ACCOUNT', value: lake.name }]
    }] }
  }
}
resource producerRawWrite 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployLab && deployProducer) {
  scope: raw
  name: guid(raw.id, producer.id, blobContributor)
  properties: { roleDefinitionId: blobContributor, principalId: producer!.identity.principalId, principalType: 'ServicePrincipal' }
}
resource producerBatchWrite 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployLab && deployProducer) {
  scope: batches
  name: guid(batches.id, producer.id, blobContributor)
  properties: { roleDefinitionId: blobContributor, principalId: producer!.identity.principalId, principalType: 'ServicePrincipal' }
}
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (deployLab) {
  scope: factory
  name: 'batch-audit'
  properties: { workspaceId: logs.id, logAnalyticsDestinationType: 'Dedicated', logs: [{ category: 'PipelineRuns', enabled: true }, { category: 'ActivityRuns', enabled: true }] }
}
resource failures 'Microsoft.Insights/metricAlerts@2018-03-01' = if (deployLab) {
  name: '${prefix}-pipeline-failed'
  location: 'global'
  tags: tags
  properties: {
    description: 'ADF failure detection; configure an approved receiver before relying on alerts.'
    severity: 2
    enabled: true
    scopes: [factory.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: { 'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria', allOf: [{ name: 'BatchFailure', metricNamespace: 'Microsoft.DataFactory/factories', metricName: 'PipelineFailedRuns', operator: 'GreaterThan', threshold: 0, timeAggregation: 'Total', criterionType: 'StaticThresholdCriterion' }] }
    actions: empty(alertActionGroupId) ? [] : [{ actionGroupId: alertActionGroupId }]
  }
}
output storageAccountName string = deployLab ? lake.name : 'not-deployed'
output factoryName string = deployLab ? factory.name : 'not-deployed'
output factoryPrincipalId string = deployLab ? factory!.identity.principalId : 'not-deployed'
output synapseWorkspaceName string = deployLab ? synapse.name : 'not-deployed'
output dedicatedPoolName string = deployLab && deployDedicatedPool ? pool.name : 'not-deployed'
