# ============================================================================
# Create Sorting Station Dashboard via ThingsBoard REST API
# ============================================================================

$TB_URL = "http://tb-dev.imespro.ai:58090"
$token = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJkdXkuaG9xdW9jQGdtYWlsLmNvbSIsInVzZXJJZCI6IjcwMDBjNDgwLTQ3NmEtMTFmMS05ODI4LTkxMTUxYjNjYjkzZiIsInNjb3BlcyI6WyJURU5BTlRfQURNSU4iXSwic2Vzc2lvbklkIjoiNGNlNTFkMDctMjYwZC00NmEwLWFkNDktYjJlMDNiODhiZmE0IiwiZXhwIjoxNzc5ODA4MTY4LCJpc3MiOiJ0aGluZ3Nib2FyZC5pbyIsImlhdCI6MTc3OTc5OTE2OCwiZmlyc3ROYW1lIjoiSOG7kyBRdeG7kWMiLCJsYXN0TmFtZSI6IkR1eSIsImVuYWJsZWQiOnRydWUsImlzUHVibGljIjpmYWxzZSwidGVuYW50SWQiOiI5YWRiMTE4MC00MmI0LTExZjAtOTY5Yy02NTA4YTZlODc2Y2EiLCJjdXN0b21lcklkIjoiMTM4MTQwMDAtMWRkMi0xMWIyLTgwODAtODA4MDgwODA4MDgwIn0.wYnNwzG3ufQpuJi4x9KtbADk2X013dn4lW-AfNSYm5u8jOny07q30ltWjugaksVJasECmXvHzP6GB4Ro5YGfRA"
$headers = @{
    "X-Authorization" = "Bearer $token"
    "Content-Type" = "application/json"
}

# Device ID for conveyor-belt
$deviceId = "eb530800-5002-11f1-9828-91151b3cb93f"

Write-Host "=== Creating Sorting Station Dashboard ===" -ForegroundColor Cyan

# Generate unique alias ID
$aliasId = [guid]::NewGuid().ToString()

# Build dashboard JSON as a HERE-STRING for precise control
$dashboardJson = @"
{
  "title": "Sorting Station Monitor - Duy",
  "configuration": {
    "description": "Industrial sorting station dashboard - real-time monitoring by Ho Quoc Duy",
    "widgets": {
      "widget_machine_state": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "Machine State",
        "sizeX": 5,
        "sizeY": 3,
        "row": 0,
        "col": 0,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "machine_state",
              "type": "timeseries",
              "label": "State",
              "settings": {},
              "color": "#2196F3"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Machine State",
          "settings": {
            "labelPosition": "top"
          }
        }
      },
      "widget_is_running": {
        "isSystemType": true,
        "bundleAlias": "gpio_widgets",
        "typeAlias": "basic_gpio_control",
        "type": "latest",
        "title": "Running Status",
        "sizeX": 3,
        "sizeY": 3,
        "row": 0,
        "col": 5,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "is_running",
              "type": "timeseries",
              "label": "Running",
              "settings": {},
              "color": "#4CAF50"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Running Status"
        }
      },
      "widget_uptime": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "System Uptime",
        "sizeX": 4,
        "sizeY": 3,
        "row": 0,
        "col": 8,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "uptime_seconds",
              "type": "timeseries",
              "label": "Uptime (s)",
              "settings": {},
              "color": "#FF9800"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "System Uptime",
          "settings": {
            "labelPosition": "top"
          }
        }
      },
      "widget_remover1": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "Remover 1 Count",
        "sizeX": 4,
        "sizeY": 3,
        "row": 3,
        "col": 0,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "remover1_count",
              "type": "timeseries",
              "label": "Remover 1",
              "settings": {},
              "color": "#2196F3"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Remover 1 Count"
        }
      },
      "widget_remover2": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "Remover 2 Count",
        "sizeX": 4,
        "sizeY": 3,
        "row": 3,
        "col": 4,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "remover2_count",
              "type": "timeseries",
              "label": "Remover 2",
              "settings": {},
              "color": "#FF9800"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Remover 2 Count"
        }
      },
      "widget_remover3": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "Remover 3 Count",
        "sizeX": 4,
        "sizeY": 3,
        "row": 3,
        "col": 8,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "remover3_count",
              "type": "timeseries",
              "label": "Remover 3",
              "settings": {},
              "color": "#4CAF50"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Remover 3 Count"
        }
      },
      "widget_vision": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "Vision Sensor",
        "sizeX": 6,
        "sizeY": 3,
        "row": 6,
        "col": 0,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [
              {"name": "vision_product_id", "type": "timeseries", "label": "Product ID", "settings": {}, "color": "#2196F3"},
              {"name": "vision_product_shape", "type": "timeseries", "label": "Shape", "settings": {}, "color": "#FF9800"},
              {"name": "vision_product_color", "type": "timeseries", "label": "Color", "settings": {}, "color": "#4CAF50"}
            ],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Vision Sensor Data"
        }
      },
      "widget_vision_ok": {
        "isSystemType": true,
        "bundleAlias": "gpio_widgets",
        "typeAlias": "basic_gpio_control",
        "type": "latest",
        "title": "Vision OK",
        "sizeX": 2,
        "sizeY": 3,
        "row": 6,
        "col": 6,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "vision_ok",
              "type": "timeseries",
              "label": "Vision",
              "settings": {},
              "color": "#4CAF50"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Vision OK"
        }
      },
      "widget_error": {
        "isSystemType": true,
        "bundleAlias": "cards",
        "typeAlias": "value_card",
        "type": "latest",
        "title": "Error Info",
        "sizeX": 4,
        "sizeY": 3,
        "row": 6,
        "col": 8,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [
              {"name": "error_code", "type": "timeseries", "label": "Error Code", "settings": {}, "color": "#F44336"},
              {"name": "error_message", "type": "timeseries", "label": "Error Message", "settings": {}, "color": "#FF5722"}
            ],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Last Error"
        }
      },
      "widget_modbus": {
        "isSystemType": true,
        "bundleAlias": "gpio_widgets",
        "typeAlias": "basic_gpio_control",
        "type": "latest",
        "title": "Modbus TCP Status",
        "sizeX": 4,
        "sizeY": 3,
        "row": 9,
        "col": 0,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "modbus_connected",
              "type": "timeseries",
              "label": "Modbus",
              "settings": {},
              "color": "#4CAF50"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Modbus TCP"
        }
      },
      "widget_mqtt": {
        "isSystemType": true,
        "bundleAlias": "gpio_widgets",
        "typeAlias": "basic_gpio_control",
        "type": "latest",
        "title": "MQTT RPC Status",
        "sizeX": 4,
        "sizeY": 3,
        "row": 9,
        "col": 4,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "mqtt_rpc_available",
              "type": "timeseries",
              "label": "MQTT RPC",
              "settings": {},
              "color": "#FF9800"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "MQTT RPC"
        }
      },
      "widget_temperature": {
        "isSystemType": true,
        "bundleAlias": "analogue_gauges",
        "typeAlias": "radial_gauge",
        "type": "latest",
        "title": "Temperature",
        "sizeX": 4,
        "sizeY": 3,
        "row": 9,
        "col": 8,
        "config": {
          "datasources": [{
            "type": "entity",
            "entityAliasId": "$aliasId",
            "dataKeys": [{
              "name": "temperature_c",
              "type": "timeseries",
              "label": "Temperature (C)",
              "settings": {},
              "color": "#F44336"
            }],
            "filterId": null
          }],
          "timewindow": {
            "realtime": { "timewindowMs": 60000 }
          },
          "showTitle": true,
          "title": "Temperature",
          "settings": {
            "minValue": 0,
            "maxValue": 80,
            "unitTitle": "C"
          }
        }
      },
      "widget_alarms": {
        "isSystemType": true,
        "bundleAlias": "alarm_widgets",
        "typeAlias": "alarms_table",
        "type": "alarm",
        "title": "Active Alarms",
        "sizeX": 12,
        "sizeY": 4,
        "row": 12,
        "col": 0,
        "config": {
          "datasources": [],
          "alarmFilterConfig": {
            "statusList": ["ACTIVE_UNACK", "ACTIVE_ACK"],
            "severityList": ["CRITICAL", "MAJOR", "MINOR", "WARNING"],
            "searchPropagatedAlarms": false
          },
          "timewindow": {
            "realtime": { "timewindowMs": 86400000 }
          },
          "showTitle": true,
          "title": "Active Alarms",
          "settings": {
            "displayDetails": true,
            "allowAcknowledgment": true,
            "allowClear": true,
            "displayPagination": true,
            "defaultPageSize": 10
          }
        }
      }
    },
    "states": {
      "default": {
        "name": "Sorting Station Monitor - Duy",
        "root": true,
        "layouts": {
          "main": {
            "widgets": {
              "widget_machine_state": { "sizeX": 5, "sizeY": 3, "mobileHeight": null, "row": 0, "col": 0 },
              "widget_is_running": { "sizeX": 3, "sizeY": 3, "mobileHeight": null, "row": 0, "col": 5 },
              "widget_uptime": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 0, "col": 8 },
              "widget_remover1": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 3, "col": 0 },
              "widget_remover2": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 3, "col": 4 },
              "widget_remover3": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 3, "col": 8 },
              "widget_vision": { "sizeX": 6, "sizeY": 3, "mobileHeight": null, "row": 6, "col": 0 },
              "widget_vision_ok": { "sizeX": 2, "sizeY": 3, "mobileHeight": null, "row": 6, "col": 6 },
              "widget_error": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 6, "col": 8 },
              "widget_modbus": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 9, "col": 0 },
              "widget_mqtt": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 9, "col": 4 },
              "widget_temperature": { "sizeX": 4, "sizeY": 3, "mobileHeight": null, "row": 9, "col": 8 },
              "widget_alarms": { "sizeX": 12, "sizeY": 4, "mobileHeight": null, "row": 12, "col": 0 }
            },
            "gridSettings": {
              "backgroundColor": "#EEEEEE",
              "columns": 12,
              "margin": 10,
              "outerMargin": true,
              "backgroundSizeMode": "100%"
            }
          }
        }
      }
    },
    "entityAliases": {
      "$aliasId": {
        "id": "$aliasId",
        "alias": "Sorting Station Device",
        "filter": {
          "type": "singleEntity",
          "resolveMultiple": false,
          "singleEntity": {
            "entityType": "DEVICE",
            "id": "$deviceId"
          }
        }
      }
    },
    "filters": {},
    "timewindow": {
      "realtime": {
        "timewindowMs": 60000
      }
    },
    "settings": {
      "stateControllerId": "entity",
      "showTitle": true,
      "showDashboardsSelect": true,
      "showEntitiesSelect": true,
      "showDashboardTimewindow": true,
      "showDashboardExport": true,
      "toolbarAlwaysOpen": true
    }
  }
}
"@

try {
    $dashboard = Invoke-RestMethod -Uri "$TB_URL/api/dashboard" -Method POST -Headers $headers -Body $dashboardJson
    $dashboardId = $dashboard.id.id
    Write-Host "Dashboard created successfully!" -ForegroundColor Green
    Write-Host "Dashboard ID: $dashboardId"
    Write-Host "Dashboard Name: $($dashboard.title)"
    Write-Host "View at: $TB_URL/dashboards/$dashboardId" -ForegroundColor Yellow
} catch {
    Write-Host "Error creating dashboard: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Response: $($_.ErrorDetails.Message)" -ForegroundColor Yellow
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
