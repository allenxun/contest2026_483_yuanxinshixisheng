# Playback review

Schematic p33 was visually reviewed: L feeds U7400/SPK1 and R feeds U7401/SPK2. They are independent amplifier inputs, not an electrical L+R sum. Both share SPK_CTL_H/GPIO2_B1 active high. Opposite-channel samples cannot electrically cancel inside one amplifier; acoustic interference between two speakers depends on placement and is not demonstrated. Actual amplifier part/gain is unverified (schematic offers alternative parts).

Real dump parsing verifies 96000 words with continuous indices. Left peak50355456=-32.60dBFS, full-buffer RMS=-55.03dBFS; right is similar. Conditional on intended DAC sample delivery, DAC-24dB and OUT2-15dB imply relative RMS about-94.03dB, not measured SPL. Thus very low amplitude plausibly explains inaudibility but is not proven alone. Arithmetic L/R averaging reduces RMS another34.9dB and must be avoided. Nonzero frames occur only at index0 modulo4; no samples were discarded or relabeled.

Codec route uses04=0c OUT2 enable,27/2a=b8 DAC route/bypass off,1a/1b=30 attenuation,30/31=14 attenuation. Replay trace19=02 has DAC unmuted. amp_low1 is the post-stop result, not active-state high proof. PIO passes source words unchanged; its bank semantics remain under separate investigation. No register-return0 claim establishes audible sound.

Root subsequently reports the user heard all three20:07 same-image tones. This supports current physical output operation for tone, narrowing replay toward amplitude/content/mapping. Smallest next gain experiment: change only matched DAC volume by+6dB, retain OUT2/PCM/routing and compare same recording. Root has requested a separate prepared-only gain candidate; no formal code changes here. A separate phase experiment could duplicate left into right without gain/zero removal, but should not be combined with the gain comparison. Never average these near-opposite channels.

Inputs and analysis.json record hashes/calculations; analyze.py is standard-library host-only and reads UART evidence, not devices. Current formal source snapshot may postdate the loaded image, whose hash is retained in supplied evidence JSON. No new board execution or audio playback was performed by this review.
