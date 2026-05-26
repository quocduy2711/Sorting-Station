# ============================================================================
# Create Sorting Station Rule Chain via ThingsBoard REST API
# ============================================================================

$TB_URL = "http://tb-dev.imespro.ai:58090"
$token = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJkdXkuaG9xdW9jQGdtYWlsLmNvbSIsInVzZXJJZCI6IjcwMDBjNDgwLTQ3NmEtMTFmMS05ODI4LTkxMTUxYjNjYjkzZiIsInNjb3BlcyI6WyJURU5BTlRfQURNSU4iXSwic2Vzc2lvbklkIjoiNGNlNTFkMDctMjYwZC00NmEwLWFkNDktYjJlMDNiODhiZmE0IiwiZXhwIjoxNzc5ODA4MTY4LCJpc3MiOiJ0aGluZ3Nib2FyZC5pbyIsImlhdCI6MTc3OTc5OTE2OCwiZmlyc3ROYW1lIjoiSOG7kyBRdeG7kWMiLCJsYXN0TmFtZSI6IkR1eSIsImVuYWJsZWQiOnRydWUsImlzUHVibGljIjpmYWxzZSwidGVuYW50SWQiOiI5YWRiMTE4MC00MmI0LTExZjAtOTY5Yy02NTA4YTZlODc2Y2EiLCJjdXN0b21lcklkIjoiMTM4MTQwMDAtMWRkMi0xMWIyLTgwODAtODA4MDgwODA4MDgwIn0.wYnNwzG3ufQpuJi4x9KtbADk2X013dn4lW-AfNSYm5u8jOny07q30ltWjugaksVJasECmXvHzP6GB4Ro5YGfRA"
$headers = @{
    "X-Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

Write-Host "=== Step 1: Create Rule Chain ===" -ForegroundColor Cyan

$ruleChainBody = @{
    name = "Sorting Station - Duy"
    type = "CORE"
    debugMode = $false
    configuration = $null
    additionalInfo = @{
        description = "Rule chain for Sorting Station project by Ho Quoc Duy"
    }
} | ConvertTo-Json -Depth 5

$ruleChain = Invoke-RestMethod -Uri "$TB_URL/api/ruleChain" -Method POST -Headers $headers -Body $ruleChainBody
$ruleChainId = $ruleChain.id.id
Write-Host "Rule Chain created: $ruleChainId" -ForegroundColor Green

Write-Host "`n=== Step 2: Add Rule Nodes (Metadata) ===" -ForegroundColor Cyan

# Build the metadata with nodes and connections
$metadataBody = @{
    ruleChainId = @{
        entityType = "RULE_CHAIN"
        id = $ruleChainId
    }
    firstNodeIndex = 0
    nodes = @(
        # Node 0: Message Type Switch
        @{
            type = "org.thingsboard.rule.engine.filter.TbMsgTypeSwitchNode"
            name = "Message Type Switch"
            debugMode = $false
            configuration = @{
                version = 0
            }
            additionalInfo = @{
                description = "Route messages by type: POST_TELEMETRY_REQUEST, POST_ATTRIBUTES_REQUEST"
                layoutX = 400
                layoutY = 150
            }
        },
        # Node 1: Save Timeseries
        @{
            type = "org.thingsboard.rule.engine.telemetry.TbMsgTimeseriesNode"
            name = "Save Timeseries"
            debugMode = $false
            configuration = @{
                defaultTTL = 0
                skipLatestPersistence = $false
                useServerTs = $false
            }
            additionalInfo = @{
                description = "Save all telemetry keys to timeseries"
                layoutX = 200
                layoutY = 350
            }
        },
        # Node 2: Save Attributes
        @{
            type = "org.thingsboard.rule.engine.telemetry.TbMsgAttributesNode"
            name = "Save Client Attributes"
            debugMode = $false
            configuration = @{
                scope = "CLIENT_SCOPE"
                notifyDevice = $false
            }
            additionalInfo = @{
                description = "Save client/shared attributes"
                layoutX = 600
                layoutY = 350
            }
        },
        # Node 3: Check Emergency Stop
        @{
            type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
            name = "Check Emergency Stop"
            debugMode = $false
            configuration = @{
                jsScript = "return msg.machine_state === 'EMERGENCY_STOP';"
            }
            additionalInfo = @{
                description = "Check if machine_state == EMERGENCY_STOP"
                layoutX = 50
                layoutY = 550
            }
        },
        # Node 4: Check Error State
        @{
            type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
            name = "Check Error State"
            debugMode = $false
            configuration = @{
                jsScript = "return msg.machine_state === 'ERROR';"
            }
            additionalInfo = @{
                description = "Check if machine_state == ERROR"
                layoutX = 250
                layoutY = 550
            }
        },
        # Node 5: Check Error Code
        @{
            type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
            name = "Check Error Code"
            debugMode = $false
            configuration = @{
                jsScript = "return msg.error_code !== undefined && msg.error_code !== null && msg.error_code !== '';"
            }
            additionalInfo = @{
                description = "Check if error_code field exists in telemetry"
                layoutX = 450
                layoutY = 550
            }
        },
        # Node 6: Check Jam or Stall
        @{
            type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
            name = "Check Jam or Stall"
            debugMode = $false
            configuration = @{
                jsScript = "return msg.is_running === false && msg.machine_state === 'RUNNING';"
            }
            additionalInfo = @{
                description = "Detect jam/stall: is_running=false but state=RUNNING"
                layoutX = 650
                layoutY = 550
            }
        },
        # Node 7: Create Alarm EMERGENCY_STOP
        @{
            type = "org.thingsboard.rule.engine.action.TbCreateAlarmNode"
            name = "Alarm: EMERGENCY_STOP"
            debugMode = $false
            configuration = @{
                useMessageAlarmData = $false
                alarmType = "EMERGENCY_STOP"
                severity = "CRITICAL"
                propagate = $true
                alarmDetailsBuildJs = "var details = {}; details.machine_state = msg.machine_state; details.source = 'Rule Chain'; return details;"
                relationTypes = @()
            }
            additionalInfo = @{
                description = "Create CRITICAL alarm for emergency stop"
                layoutX = 50
                layoutY = 750
            }
        },
        # Node 8: Create Alarm SYSTEM_ERROR
        @{
            type = "org.thingsboard.rule.engine.action.TbCreateAlarmNode"
            name = "Alarm: SYSTEM_ERROR"
            debugMode = $false
            configuration = @{
                useMessageAlarmData = $false
                alarmType = "SYSTEM_ERROR"
                severity = "MAJOR"
                propagate = $true
                alarmDetailsBuildJs = "var details = {}; details.machine_state = msg.machine_state; details.error_code = msg.error_code || 'UNKNOWN'; details.error_message = msg.error_message || ''; return details;"
                relationTypes = @()
            }
            additionalInfo = @{
                description = "Create MAJOR alarm for system error"
                layoutX = 250
                layoutY = 750
            }
        },
        # Node 9: Create Alarm Error Code
        @{
            type = "org.thingsboard.rule.engine.action.TbCreateAlarmNode"
            name = "Alarm: Error Code"
            debugMode = $false
            configuration = @{
                useMessageAlarmData = $false
                alarmType = "DEVICE_ERROR"
                severity = "MAJOR"
                propagate = $true
                alarmDetailsBuildJs = "var details = {}; details.error_code = msg.error_code; details.error_message = msg.error_message; details.machine_state = msg.machine_state; return details;"
                relationTypes = @()
            }
            additionalInfo = @{
                description = "Create alarm from error_code field"
                layoutX = 450
                layoutY = 750
            }
        },
        # Node 10: Create Alarm JAM_OR_STALL
        @{
            type = "org.thingsboard.rule.engine.action.TbCreateAlarmNode"
            name = "Alarm: JAM_OR_STALL"
            debugMode = $false
            configuration = @{
                useMessageAlarmData = $false
                alarmType = "JAM_OR_STALL"
                severity = "MAJOR"
                propagate = $true
                alarmDetailsBuildJs = "var details = {}; details.machine_state = msg.machine_state; details.is_running = msg.is_running; return details;"
                relationTypes = @()
            }
            additionalInfo = @{
                description = "Create MAJOR alarm for jam/stall"
                layoutX = 650
                layoutY = 750
            }
        },
        # Node 11: Check Running Normal
        @{
            type = "org.thingsboard.rule.engine.filter.TbJsFilterNode"
            name = "Check Running Normal"
            debugMode = $false
            configuration = @{
                jsScript = "return msg.machine_state === 'RUNNING' && msg.is_running === true && (msg.error_code === undefined || msg.error_code === null || msg.error_code === '');"
            }
            additionalInfo = @{
                description = "Check if system is running normally (for alarm clearing)"
                layoutX = 850
                layoutY = 550
            }
        },
        # Node 12: Clear Alarms
        @{
            type = "org.thingsboard.rule.engine.action.TbClearAlarmNode"
            name = "Clear Alarms"
            debugMode = $false
            configuration = @{
                alarmType = "EMERGENCY_STOP"
                alarmDetailsBuildJs = "var details = {}; details.cleared_by = 'Rule Chain'; details.machine_state = msg.machine_state; return details;"
            }
            additionalInfo = @{
                description = "Clear alarms when machine returns to RUNNING normally"
                layoutX = 850
                layoutY = 750
            }
        }
    )
    connections = @(
        # Message Type Switch -> Save Timeseries (Post telemetry)
        @{ fromIndex = 0; toIndex = 1; type = "Post telemetry" },
        # Message Type Switch -> Save Attributes (Post attributes)
        @{ fromIndex = 0; toIndex = 2; type = "Post attributes" },
        # Save Timeseries -> Check Emergency Stop
        @{ fromIndex = 1; toIndex = 3; type = "Success" },
        # Save Timeseries -> Check Error State
        @{ fromIndex = 1; toIndex = 4; type = "Success" },
        # Save Timeseries -> Check Error Code
        @{ fromIndex = 1; toIndex = 5; type = "Success" },
        # Save Timeseries -> Check Jam/Stall
        @{ fromIndex = 1; toIndex = 6; type = "Success" },
        # Save Timeseries -> Check Running Normal
        @{ fromIndex = 1; toIndex = 11; type = "Success" },
        # Check Emergency Stop -> Alarm EMERGENCY_STOP
        @{ fromIndex = 3; toIndex = 7; type = "True" },
        # Check Error State -> Alarm SYSTEM_ERROR
        @{ fromIndex = 4; toIndex = 8; type = "True" },
        # Check Error Code -> Alarm Error Code
        @{ fromIndex = 5; toIndex = 9; type = "True" },
        # Check Jam/Stall -> Alarm JAM_OR_STALL
        @{ fromIndex = 6; toIndex = 10; type = "True" },
        # Check Running Normal -> Clear Alarms
        @{ fromIndex = 11; toIndex = 12; type = "True" }
    )
    ruleChainConnections = $null
} | ConvertTo-Json -Depth 10

try {
    $metadataResult = Invoke-RestMethod -Uri "$TB_URL/api/ruleChain/metadata" -Method POST -Headers $headers -Body $metadataBody
    Write-Host "Rule Chain metadata saved successfully!" -ForegroundColor Green
    Write-Host "Rule Chain ID: $ruleChainId"
} catch {
    Write-Host "Error saving metadata: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Response: $($_.ErrorDetails.Message)" -ForegroundColor Yellow
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Rule Chain Name: Sorting Station - Duy"
Write-Host "Rule Chain ID: $ruleChainId"
Write-Host "View at: $TB_URL/ruleChains/$ruleChainId"
