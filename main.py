from cmg_query import CmgQuery


def main():
    cmg = CmgQuery()
    cmg.connect()
    cmg.test_bfd_sessions()
    cmg.test_pings()
    cmg.disconnect()
    cmg.dump_to_outfile()


def my_print():
    print("Hello World")


if __name__ == "__main__":
    main()
    my_print()
    print("Finished")

