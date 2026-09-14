job "bambooai-executor-free" {
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
      stop_on_client_after = "30m"
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
        memory_hard_limit = 4096  # 4GB hard limit
      }
      
      resources {
        cpu    = 200   # 0.2 cores
        memory = 4096  # 4GB
      }
      
      env {
        USER_ID = "${NOMAD_META_user_id}"
        SESSION_ID = "${NOMAD_META_session_id}"
        USER_TIER = "free"
        FLASK_ENV = "production"
        
        JOBLIB_N_JOBS = "2"
        OMP_NUM_THREADS = "2"
        MKL_NUM_THREADS = "2"
      }
      
      service {
        name = "bambooai-executor-${NOMAD_META_user_id}"
        port = "executor"
        
        tags = [
          "bambooai",
          "executor", 
          "user-${NOMAD_META_user_id}",
          "tier-free"
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
