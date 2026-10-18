def lzo1x_decompress(src, out_len):
    out = bytearray(); ip = 0; n = len(src)
    def cp_match(dist, length):
        start = len(out) - dist
        if start < 0: raise ValueError('lookbehind')
        for i in range(length): out.append(out[start + i])
    t = src[ip]
    state = 0
    if t > 17:
        t -= 17; ip += 1
        out += src[ip:ip+t]; ip += t
        state = 4 if t >= 4 else t
        # fallthrough to match loop
    else:
        pass
    first = (src[0] > 17)
    while ip < n:
        t = src[ip]; ip += 1
        if t < 16:
            if state == 0:
                # literal run
                if t == 0:
                    while src[ip] == 0: t += 255; ip += 1
                    t += 15 + src[ip]; ip += 1
                t += 3
                out += src[ip:ip+t]; ip += t
                state = 4
                continue
            elif state < 4:
                # 2-byte match dist <= 1024
                dist = 1 + (t >> 2) + (src[ip] << 2); ip += 1
                cp_match(dist, 2)
            else:
                dist = 1 + 0x800 + (t >> 2) + (src[ip] << 2); ip += 1
                cp_match(dist, 3)
            state = t & 3
            out += src[ip:ip+state]; ip += state
            continue
        if t >= 64:
            nxt = t & 3
            length = (t >> 5) + 1
            dist = 1 + ((t >> 2) & 7) + (src[ip] << 3); ip += 1
        elif t >= 32:
            length = t & 31
            if length == 0:
                while src[ip] == 0: length += 255; ip += 1
                length += 31 + src[ip]; ip += 1
            length += 2
            d = src[ip] | (src[ip+1] << 8); ip += 2
            dist = 1 + (d >> 2)
            cp_match(dist, length)
            state = d & 3
            out += src[ip:ip+state]; ip += state
            continue
        else:
            length = t & 7
            if length == 0:
                while src[ip] == 0: length += 255; ip += 1
                length += 7 + src[ip]; ip += 1
            length += 2
            d = src[ip] | (src[ip+1] << 8); ip += 2
            dist = ((t & 8) << 11) + (d >> 2)
            if dist == 0:
                break  # end of stream
            dist += 0x4000
            cp_match(dist, length)
            state = d & 3
            out += src[ip:ip+state]; ip += state
            continue
        cp_match(dist, length)
        state = nxt
        out += src[ip:ip+state]; ip += state
    return bytes(out)
