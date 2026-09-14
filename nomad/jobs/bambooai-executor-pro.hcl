job "bambooai-executor-pro" {
  datacenters = ["dc1"]
  type = "batch"
  
  parameterized {
    payload = "optional"
    meta_required = ["user_id"]
    meta_optional = ["session_id"]
  }
  
  group "executor" {
    count = 1

    disconnect {
      stop_on_client_after = "1h"
    }
    
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
        memory_hard_limit = 16384  # 16GB hard limit
      }
      
      resources {
        cpu    = 800    # 0.8 cores
        memory = 16384  # 16GB
      }
      
      env {
        USER_ID = "${NOMAD_META_user_id}"
        SESSION_ID = "${NOMAD_META_session_id}"
        USER_TIER = "pro"
        FLASK_ENV = "production"
        
        JOBLIB_N_JOBS = "4"
        OMP_NUM_THREADS = "4"
        MKL_NUM_THREADS = "4"
      }
      
      service {
        name = "bambooai-executor-${NOMAD_META_user_id}"
        port = "executor"
        
        tags = [
          "bambooai",
          "executor", 
          "user-${NOMAD_META_user_id}",
          "tier-pro"
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
      
      kill_timeout = "30s"
      kill_signal = "SIGTERM"
    }
  }
}
