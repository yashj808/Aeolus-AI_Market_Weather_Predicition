import uvicorn
import config

def main():
    print(f"Starting Hermes Weather Agent Web Server on port {config.PORT}...")
    # Run uvicorn web server hosting FastAPI
    uvicorn.run(
        "api.main:app", 
        host="0.0.0.0", 
        port=config.PORT, 
        reload=False
    )

if __name__ == "__main__":
    main()
