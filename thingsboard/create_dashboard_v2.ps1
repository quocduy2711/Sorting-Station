# ============================================================================
# Recreate Sorting Station Dashboard with CORRECT ThingsBoard widget format
# Based on actual working dashboard reference from the server
# ============================================================================

$TB_URL = "http://tb-dev.imespro.ai:58090"
$token = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJkdXkuaG9xdW9jQGdtYWlsLmNvbSIsInVzZXJJZCI6IjcwMDBjNDgwLTQ3NmEtMTFmMS05ODI4LTkxMTUxYjNjYjkzZiIsInNjb3BlcyI6WyJURU5BTlRfQURNSU4iXSwic2Vzc2lvbklkIjoiNGNlNTFkMDctMjYwZC00NmEwLWFkNDktYjJlMDNiODhiZmE0IiwiZXhwIjoxNzc5ODA4MTY4LCJpc3MiOiJ0aGluZ3Nib2FyZC5pbyIsImlhdCI6MTc3OTc5OTE2OCwiZmlyc3ROYW1lIjoiSOG7kyBRdeG7kWMiLCJsYXN0TmFtZSI6IkR1eSIsImVuYWJsZWQiOnRydWUsImlzUHVibGljIjpmYWxzZSwidGVuYW50SWQiOiI5YWRiMTE4MC00MmI0LTExZjAtOTY5Yy02NTA4YTZlODc2Y2EiLCJjdXN0b21lcklkIjoiMTM4MTQwMDAtMWRkMi0xMWIyLTgwODAtODA4MDgwODA4MDgwIn0.wYnNwzG3ufQpuJi4x9KtbADk2X013dn4lW-AfNSYm5u8jOny07q30ltWjugaksVJasECmXvHzP6GB4Ro5YGfRA"
$headers = @{
    "X-Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

$deviceId = "eb530800-5002-11f1-9828-91151b3cb93f"
$aliasId = "ss-alias-" + [guid]::NewGuid().ToString().Substring(0,8)

Write-Host "=== Creating Sorting Station Dashboard (Fixed Format) ===" -ForegroundColor Cyan
Write-Host "Alias ID: $aliasId"

# --- Helper function to create a value_card widget ---
function New-ValueCardWidget {
    param(
        [string]$Id,
        [string]$Label,
        [string]$DataKey,
        [string]$Icon,
        [string]$IconColor,
        [string]$AliasId,
        [int]$SizeX, [int]$SizeY, [int]$Row, [int]$Col,
        [int]$Decimals = 0,
        [string]$Units = ""
    )
    return @{
        typeFullFqn = "system.cards.value_card"
        type = "latest"
        sizeX = $SizeX
        sizeY = $SizeY
        row = $Row
        col = $Col
        id = $Id
        config = @{
            datasources = @(
                @{
                    type = "entity"
                    name = ""
                    entityAliasId = $AliasId
                    dataKeys = @(
                        @{
                            name = $DataKey
                            type = "timeseries"
                            label = $Label
                            color = "#2196f3"
                            settings = @{}
                            _hash = 0.123
                        }
                    )
                    alarmFilterConfig = @{
                        statusList = @("ACTIVE")
                    }
                }
            )
            timewindow = @{
                displayValue = ""
                selectedTab = 0
                realtime = @{
                    realtimeType = 1
                    interval = 1000
                    timewindowMs = 60000
                    quickInterval = "CURRENT_DAY"
                }
                aggregation = @{
                    type = "NONE"
                    limit = 25000
                }
            }
            showTitle = $false
            backgroundColor = "rgba(0, 0, 0, 0)"
            color = "rgba(0, 0, 0, 0.87)"
            padding = "0px"
            settings = @{
                labelPosition = "top"
                layout = "square"
                showLabel = $true
                labelFont = @{ family = "Roboto"; size = 16; sizeUnit = "px"; style = "normal"; weight = "500" }
                labelColor = @{ type = "constant"; color = "rgba(0, 0, 0, 0.87)" }
                showIcon = $true
                iconSize = 40
                iconSizeUnit = "px"
                icon = $Icon
                iconColor = @{ type = "constant"; color = $IconColor }
                valueFont = @{ family = "Roboto"; size = 52; sizeUnit = "px"; style = "normal"; weight = "500" }
                valueColor = @{ type = "constant"; color = "rgba(0, 0, 0, 0.87)" }
                showDate = $true
                dateFormat = @{ format = $null; lastUpdateAgo = $true; custom = $false }
                dateFont = @{ family = "Roboto"; size = 12; sizeUnit = "px"; style = "normal"; weight = "500" }
                dateColor = @{ type = "constant"; color = "rgba(0, 0, 0, 0.38)" }
                background = @{
                    type = "color"
                    color = "#fff"
                    overlay = @{ enabled = $false; color = "rgba(255,255,255,0.72)"; blur = 3 }
                }
                autoScale = $true
            }
            title = $Label
            dropShadow = $true
            enableFullscreen = $false
            units = $Units
            decimals = $Decimals
            useDashboardTimewindow = $true
            showLegend = $false
            configMode = "basic"
            displayTimewindow = $true
            margin = "0px"
            borderRadius = "0px"
            widgetCss = ""
            pageSize = 1024
            noDataDisplayMessage = ""
            showTitleIcon = $false
            titleTooltip = ""
            widgetStyle = @{}
            actions = @{}
        }
    }
}

# --- Helper function to create a status_widget ---
function New-StatusWidget {
    param(
        [string]$Id,
        [string]$Label,
        [string]$DataKey,
        [string]$AliasId,
        [int]$SizeX, [int]$SizeY, [int]$Row, [int]$Col
    )
    return @{
        typeFullFqn = "system.cards.value_card"
        type = "latest"
        sizeX = $SizeX
        sizeY = $SizeY
        row = $Row
        col = $Col
        id = $Id
        config = @{
            datasources = @(
                @{
                    type = "entity"
                    name = ""
                    entityAliasId = $AliasId
                    dataKeys = @(
                        @{
                            name = $DataKey
                            type = "timeseries"
                            label = $Label
                            color = "#4CAF50"
                            settings = @{}
                            _hash = 0.456
                        }
                    )
                    alarmFilterConfig = @{
                        statusList = @("ACTIVE")
                    }
                }
            )
            timewindow = @{
                displayValue = ""
                selectedTab = 0
                realtime = @{
                    realtimeType = 1
                    interval = 1000
                    timewindowMs = 60000
                    quickInterval = "CURRENT_DAY"
                }
                aggregation = @{
                    type = "NONE"
                    limit = 25000
                }
            }
            showTitle = $false
            backgroundColor = "rgba(0, 0, 0, 0)"
            color = "rgba(0, 0, 0, 0.87)"
            padding = "0px"
            settings = @{
                labelPosition = "top"
                layout = "square"
                showLabel = $true
                labelFont = @{ family = "Roboto"; size = 16; sizeUnit = "px"; style = "normal"; weight = "500" }
                labelColor = @{ type = "constant"; color = "rgba(0, 0, 0, 0.87)" }
                showIcon = $true
                iconSize = 40
                iconSizeUnit = "px"
                icon = "sensors"
                iconColor = @{ type = "constant"; color = "#4CAF50" }
                valueFont = @{ family = "Roboto"; size = 52; sizeUnit = "px"; style = "normal"; weight = "500" }
                valueColor = @{ type = "constant"; color = "rgba(0, 0, 0, 0.87)" }
                showDate = $true
                dateFormat = @{ format = $null; lastUpdateAgo = $true; custom = $false }
                dateFont = @{ family = "Roboto"; size = 12; sizeUnit = "px"; style = "normal"; weight = "500" }
                dateColor = @{ type = "constant"; color = "rgba(0, 0, 0, 0.38)" }
                background = @{
                    type = "color"
                    color = "#fff"
                    overlay = @{ enabled = $false; color = "rgba(255,255,255,0.72)"; blur = 3 }
                }
                autoScale = $true
            }
            title = $Label
            dropShadow = $true
            enableFullscreen = $false
            units = ""
            decimals = 0
            useDashboardTimewindow = $true
            showLegend = $false
            configMode = "basic"
            displayTimewindow = $true
            margin = "0px"
            borderRadius = "0px"
            widgetCss = ""
            pageSize = 1024
            noDataDisplayMessage = ""
            showTitleIcon = $false
            titleTooltip = ""
            widgetStyle = @{}
            actions = @{}
        }
    }
}

# --- Build all widgets --- (24 column grid like reference)
$widgets = @{}
$layoutWidgets = @{}

# Row 0: Machine State, Running, Uptime (3 cards)
$w1id = "w-machine-state"
$widgets[$w1id] = New-ValueCardWidget -Id $w1id -Label "Machine State" -DataKey "machine_state" -Icon "precision_manufacturing" -IconColor "#2196F3" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 0 -Col 0
$layoutWidgets[$w1id] = @{ sizeX = 8; sizeY = 3; row = 0; col = 0 }

$w2id = "w-is-running"
$widgets[$w2id] = New-StatusWidget -Id $w2id -Label "Running" -DataKey "is_running" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 0 -Col 8
$layoutWidgets[$w2id] = @{ sizeX = 8; sizeY = 3; row = 0; col = 8 }

$w3id = "w-uptime"
$widgets[$w3id] = New-ValueCardWidget -Id $w3id -Label "Uptime (s)" -DataKey "uptime_seconds" -Icon "timer" -IconColor "#FF9800" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 0 -Col 16 -Decimals 1 -Units "s"
$layoutWidgets[$w3id] = @{ sizeX = 8; sizeY = 3; row = 0; col = 16 }

# Row 3: Remover 1, 2, 3
$w4id = "w-remover1"
$widgets[$w4id] = New-ValueCardWidget -Id $w4id -Label "Remover 1" -DataKey "remover1_count" -Icon "filter_1" -IconColor "#2196F3" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 3 -Col 0
$layoutWidgets[$w4id] = @{ sizeX = 8; sizeY = 3; row = 3; col = 0 }

$w5id = "w-remover2"
$widgets[$w5id] = New-ValueCardWidget -Id $w5id -Label "Remover 2" -DataKey "remover2_count" -Icon "filter_2" -IconColor "#FF9800" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 3 -Col 8
$layoutWidgets[$w5id] = @{ sizeX = 8; sizeY = 3; row = 3; col = 8 }

$w6id = "w-remover3"
$widgets[$w6id] = New-ValueCardWidget -Id $w6id -Label "Remover 3" -DataKey "remover3_count" -Icon "filter_3" -IconColor "#4CAF50" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 3 -Col 16
$layoutWidgets[$w6id] = @{ sizeX = 8; sizeY = 3; row = 3; col = 16 }

# Row 6: Vision Product, Vision OK, Temperature
$w7id = "w-vision-product"
$widgets[$w7id] = New-ValueCardWidget -Id $w7id -Label "Vision Product" -DataKey "vision_product_shape" -Icon "visibility" -IconColor "#9C27B0" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 6 -Col 0
$layoutWidgets[$w7id] = @{ sizeX = 8; sizeY = 3; row = 6; col = 0 }

$w8id = "w-vision-ok"
$widgets[$w8id] = New-StatusWidget -Id $w8id -Label "Vision OK" -DataKey "vision_ok" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 6 -Col 8
$layoutWidgets[$w8id] = @{ sizeX = 8; sizeY = 3; row = 6; col = 8 }

$w9id = "w-temperature"
$widgets[$w9id] = New-ValueCardWidget -Id $w9id -Label "Temperature" -DataKey "temperature_c" -Icon "thermostat" -IconColor "#F44336" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 6 -Col 16 -Decimals 1 -Units "C"
$layoutWidgets[$w9id] = @{ sizeX = 8; sizeY = 3; row = 6; col = 16 }

# Row 9: Modbus, MQTT, Error
$w10id = "w-modbus"
$widgets[$w10id] = New-StatusWidget -Id $w10id -Label "Modbus TCP" -DataKey "modbus_connected" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 9 -Col 0
$layoutWidgets[$w10id] = @{ sizeX = 8; sizeY = 3; row = 9; col = 0 }

$w11id = "w-mqtt"
$widgets[$w11id] = New-StatusWidget -Id $w11id -Label "MQTT RPC" -DataKey "mqtt_rpc_available" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 9 -Col 8
$layoutWidgets[$w11id] = @{ sizeX = 8; sizeY = 3; row = 9; col = 8 }

$w12id = "w-error-code"
$widgets[$w12id] = New-ValueCardWidget -Id $w12id -Label "Error Code" -DataKey "error_code" -Icon "error" -IconColor "#F44336" -AliasId $aliasId -SizeX 8 -SizeY 3 -Row 9 -Col 16
$layoutWidgets[$w12id] = @{ sizeX = 8; sizeY = 3; row = 9; col = 16 }

# --- Build the full dashboard object ---
$dashboard = @{
    title = "Sorting Station Monitor - Duy"
    configuration = @{
        description = "Industrial Sorting Station - Real-time Monitoring Dashboard by Ho Quoc Duy"
        widgets = $widgets
        states = @{
            default = @{
                name = "Sorting Station Monitor - Duy"
                root = $true
                layouts = @{
                    main = @{
                        widgets = $layoutWidgets
                        gridSettings = @{
                            layoutType = "default"
                            backgroundColor = "#eeeeee"
                            columns = 24
                            margin = 10
                            outerMargin = $true
                            backgroundSizeMode = "100%"
                        }
                    }
                }
            }
        }
        entityAliases = @{
            $aliasId = @{
                id = $aliasId
                alias = "Sorting Station Device"
                filter = @{
                    type = "singleEntity"
                    resolveMultiple = $false
                    singleEntity = @{
                        entityType = "DEVICE"
                        id = $deviceId
                    }
                }
            }
        }
        filters = @{}
        timewindow = @{
            displayValue = ""
            selectedTab = 0
            realtime = @{
                realtimeType = 1
                interval = 1000
                timewindowMs = 60000
                quickInterval = "CURRENT_DAY"
            }
            aggregation = @{
                type = "NONE"
                limit = 25000
            }
        }
        settings = @{
            stateControllerId = "entity"
            showTitle = $true
            showDashboardsSelect = $true
            showEntitiesSelect = $true
            showDashboardTimewindow = $true
            showDashboardExport = $true
            toolbarAlwaysOpen = $true
        }
    }
} | ConvertTo-Json -Depth 20

try {
    $result = Invoke-RestMethod -Uri "$TB_URL/api/dashboard" -Method POST -Headers $headers -Body $dashboard
    $dashId = $result.id.id
    Write-Host "`nDashboard created successfully!" -ForegroundColor Green
    Write-Host "Dashboard ID: $dashId"
    Write-Host "Dashboard URL: $TB_URL/dashboards/$dashId" -ForegroundColor Yellow
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Details: $($_.ErrorDetails.Message)" -ForegroundColor Yellow
}
