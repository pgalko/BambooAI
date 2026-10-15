job "bambooai-executor" {
  datacenters = ["dc1"]
  type = "batch"  # Keep as "batch" for parameterized support
  
  # Parameterized job for user-specific containers
  parameterized {
    payload = "optional"
    meta_required = ["user_id"]
    meta_optional = ["session_id"]
  }
  
  group "executor" {
    count = 1

    # Use modern disconnect block for 1 Hour auto-stop after disconnect (replaces deprecated stop_after_client_disconnect)
    disconnect {
      stop_on_client_after = "1h"
    }
    
    # Automatic job cleanup (batch-specific)
    reschedule {
      attempts = 0
      unlimited = false
    }
    
    restart {
      attempts = 1
      interval = "5m"
      delay = "15s"
      mode = "fail"
    }
    
    network {
      port "executor" {
        to = 5000
      }
    }
    
    task "pandas-api" {
      driver = "docker"
      
      config {
        image = "localhost:5000/bambooai-executor:latest"
        ports = ["executor"]
        
        force_pull = false
        privileged = false

        # Hard kernel limits - cannot be overridden by code
        memory_hard_limit = 16384

        # The executor's datasets - the Intervals.icu store and the loaded windows' files - in a Docker volume of the
        # user's own, created on first use with the image's ownership and kept across dispatches, so a load downloads
        # only what the store lacks (docs/INCREMENTAL_LOADS_DESIGN.md §3, 2026-10-15). volume_driver makes the entry a
        # named volume: without it Nomad reads a relative source as a folder inside the allocation directory, which
        # goes with the allocation. Needs `plugin "docker" { config { volumes { enabled = true } } }` in the client's
        # configuration. A volume lives on the node that made it: a cluster of several client nodes needs a shared
        # volume driver or a node constraint for the store to follow the user.
        volume_driver = "local"
        volumes = ["bambooai-datasets-${NOMAD_META_user_id}:/app/datasets"]
      }
      
      resources {
        cpu    = 800   # 0.8 cores guaranteed
        memory = 16384
      }
      
      env {
        USER_ID = "${NOMAD_META_user_id}"
        SESSION_ID = "${NOMAD_META_session_id}"
        FLASK_ENV = "production"
        
        # Keep these - they work for cooperative libraries
        JOBLIB_N_JOBS = "4"       # Match cpu_quota
        OMP_NUM_THREADS = "4"     # Match cpu_quota  
        MKL_NUM_THREADS = "4"     # Match cpu_quota
      }
      
      # Service discovery
      service {
        name = "bambooai-executor-${NOMAD_META_user_id}"
        port = "executor"
        
        tags = [
          "bambooai",
          "executor", 
          "user-${NOMAD_META_user_id}"
        ]
        
        check {
          type     = "http"
          path     = "/health"
          interval = "10s"
          timeout  = "5s"
          check_restart {
            limit = 3
            grace = "30s"
          }
        }
      }
      
      # Graceful shutdown
      kill_timeout = "30s"
      kill_signal = "SIGTERM"
    }
  }
}
