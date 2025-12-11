# Court_System
Codechef interview project
after opening the server the documennts can be founnd in 
http://127.0.0.1:8000/docs
This is the autodocumentation of FastAPI
Here,We are using a postgres data base named "Court_system" and it should contain tables named "users","votes" and "cases"
We also use JWT Bearer authentication 
run "py -m uvicorn mainn:app -reload" in the power shell(in the virtual environment) to start the server


Possible future improvements:
1) make the voting annonymous for jurors
2) after the judge makes changes automtically change the status of the case approval back to pending.
3) Autogenerationg of secret key instead of hardcoding it

below given postman collection might make testing easier: 
https://shashwatj0107-9790495.postman.co/workspace/Personal-Workspace~ac403138-74dd-414e-bf85-2eeb399d9f30/collection/48426681-c2dc74c2-38db-44aa-9d4d-1f957ddbdf66?action=share&creator=48426681
