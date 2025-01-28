from win11toast import toast


def on_click(response):
    print(response)
    if response["arguments"] == "http:Yes":
        print("User clicked Yes")
    elif response["arguments"] == "http:No":
        print("User clicked No")


toast("Question", "Do you want to continue?", buttons=["Yes", "No"], on_click=on_click)
