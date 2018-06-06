from inotify_simple import INotify, flags


inotify = INotify()
watch_flags = flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF
wd = inotify.add_watch(b'/home/ucfabb0/semantica/to_process', mask=watch_flags)


def _main():
    # And see the corresponding events:
    for event in inotify.read():
        print(event)
        for flag in flags.from_mask(event.mask):
            print('    ' + str(flag))


if __name__ == '__main__':
    _main()
